use crate::{
    addons::{csi::CSIComponent, ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum::{self, ClusterError},
};
use docker_image::DockerImage;
use include_dir::include_dir;
use k8s_openapi::api::core::v1::{KeyToPath, SecretVolumeSource, Toleration, Volume, VolumeMount};
use maplit::btreemap;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIValues {
    csimanila: CSIComponent,
    nodeplugin: CSINodePlugin,
    controllerplugin: CSIControllerPlugin,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSINodePlugin {
    registrar: CSIComponent,
    tolerations: Vec<Toleration>,
    volumes: Vec<Volume>,

    #[serde(rename = "volumeMounts")]
    volume_mounts: Vec<VolumeMount>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIControllerPlugin {
    provisioner: CSIComponent,
    snapshotter: CSIComponent,
    resizer: CSIComponent,
    tolerations: Vec<Toleration>,
    volumes: Vec<Volume>,

    #[serde(rename = "volumeMounts")]
    volume_mounts: Vec<VolumeMount>,
}

impl ClusterAddonValues for CSIValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/openstack-manila-csi/values.yaml"
        ));
        let values: Self = serde_yaml::from_str(file)?;

        Ok(values)
    }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => format!(
                "{}/{}",
                registry.trim_end_matches('/'),
                image.name.split('/').next_back().unwrap()
            ),
            None => image.to_string(),
        }
    }
}

impl TryFrom<magnum::Cluster> for CSIValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let values = Self::defaults()?;

        Ok(Self {
            csimanila: CSIComponent {
                image: values
                    .csimanila
                    .image
                    .using_cluster::<Self>(&cluster, &cluster.labels.manila_csi_plugin_tag)?,
            },
            nodeplugin: CSINodePlugin {
                registrar: CSIComponent {
                    image: values.nodeplugin.registrar.image.using_cluster::<Self>(
                        &cluster,
                        &cluster.labels.csi_node_driver_registrar_tag,
                    )?,
                },
                tolerations: vec![Toleration {
                    operator: Some("Exists".to_string()),
                    ..Default::default()
                }],
                volumes: vec![],
                volume_mounts: vec![],
            },
            controllerplugin: CSIControllerPlugin {
                provisioner: CSIComponent {
                    image: values
                        .controllerplugin
                        .provisioner
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_provisioner_tag)?,
                },
                snapshotter: CSIComponent {
                    image: values
                        .controllerplugin
                        .snapshotter
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_snapshotter_tag)?,
                },
                resizer: CSIComponent {
                    image: values
                        .controllerplugin
                        .resizer
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_resizer_tag)?,
                },
                tolerations: vec![
                    Toleration {
                        key: Some("node-role.kubernetes.io/master".to_string()),
                        effect: Some("NoSchedule".to_string()),
                        ..Default::default()
                    },
                    Toleration {
                        key: Some("node-role.kubernetes.io/control-plane".to_string()),
                        effect: Some("NoSchedule".to_string()),
                        ..Default::default()
                    },
                ],
                volumes: vec![Volume {
                    name: "cloud-config".into(),
                    secret: Some(SecretVolumeSource {
                        secret_name: Some("cloud-config".into()),
                        default_mode: Some(420),
                        items: Some(vec![KeyToPath {
                            key: "ca.crt".into(),
                            path: "ca.crt".into(),
                            ..Default::default()
                        }]),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
                volume_mounts: vec![VolumeMount {
                    name: "cloud-config".into(),
                    mount_path: "/etc/config".into(),
                    read_only: Some(true),
                    ..Default::default()
                }],
            },
        })
    }
}

pub struct Addon {
    cluster: magnum::Cluster,
}

impl Addon {}

impl ClusterAddon for Addon {
    fn new(cluster: magnum::Cluster) -> Self {
        Self { cluster }
    }

    fn enabled(&self) -> bool {
        self.cluster.labels.manila_csi_enabled.eq_ignore_ascii_case("true")
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-manila-csi", self.cluster.stack_id()?))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        let values = &CSIValues::try_from(self.cluster.clone()).expect("failed to create values");

        Ok(btreemap! {
            "manila-csi.yaml".to_owned() => helm::template_using_include_dir(
                include_dir!("magnum_cluster_api/charts/openstack-manila-csi"),
                "manila-csi",
                "kube-system",
                values,
            )?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::addons::ImageDetails;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_manila_csi_values_for_cluster_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: CSIValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.csimanila.image,
            ImageDetails {
                repository: "registry.k8s.io/provider-os/manila-csi-plugin".into(),
                tag: cluster.labels.manila_csi_plugin_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.nodeplugin.registrar.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-node-driver-registrar".into(),
                tag: cluster.labels.csi_node_driver_registrar_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.controllerplugin.provisioner.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-provisioner".into(),
                tag: cluster.labels.csi_provisioner_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.controllerplugin.snapshotter.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-snapshotter".into(),
                tag: cluster.labels.csi_snapshotter_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.controllerplugin.resizer.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-resizer".into(),
                tag: cluster.labels.csi_resizer_tag,
                use_digest: Some(true),
            }
        );
    }

    #[test]
    fn test_manila_csi_values_for_cluster_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: CSIValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.csimanila.image,
            ImageDetails {
                repository: "registry.example.com/manila-csi-plugin".into(),
                tag: cluster.labels.manila_csi_plugin_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.nodeplugin.registrar.image,
            ImageDetails {
                repository: "registry.example.com/csi-node-driver-registrar".into(),
                tag: cluster.labels.csi_node_driver_registrar_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.controllerplugin.provisioner.image,
            ImageDetails {
                repository: "registry.example.com/csi-provisioner".into(),
                tag: cluster.labels.csi_provisioner_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.controllerplugin.snapshotter.image,
            ImageDetails {
                repository: "registry.example.com/csi-snapshotter".into(),
                tag: cluster.labels.csi_snapshotter_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.controllerplugin.resizer.image,
            ImageDetails {
                repository: "registry.example.com/csi-resizer".into(),
                tag: cluster.labels.csi_resizer_tag,
                use_digest: Some(false),
            }
        );
    }

    #[test]
    fn test_common_cinder_csi_values_for_cluster() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: CSIValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.nodeplugin.tolerations,
            vec![Toleration {
                operator: Some("Exists".to_string()),
                ..Default::default()
            }]
        );
        assert_eq!(
            values.controllerplugin.tolerations,
            vec![
                Toleration {
                    key: Some("node-role.kubernetes.io/master".to_string()),
                    effect: Some("NoSchedule".to_string()),
                    ..Default::default()
                },
                Toleration {
                    key: Some("node-role.kubernetes.io/control-plane".to_string()),
                    effect: Some("NoSchedule".to_string()),
                    ..Default::default()
                },
            ]
        );
        assert_eq!(
            values.controllerplugin.volumes,
            vec![Volume {
                name: "cloud-config".into(),
                secret: Some(SecretVolumeSource {
                    secret_name: Some("cloud-config".into()),
                    default_mode: Some(420),
                    items: Some(vec![KeyToPath {
                        key: "ca.crt".into(),
                        path: "ca.crt".into(),
                        ..Default::default()
                    }]),
                    ..Default::default()
                }),
                ..Default::default()
            }]
        );
        assert_eq!(
            values.controllerplugin.volume_mounts,
            vec![VolumeMount {
                name: "cloud-config".into(),
                mount_path: "/etc/config".into(),
                read_only: Some(true),
                ..Default::default()
            }]
        );
        assert_eq!(values.nodeplugin.volumes, vec![]);
        assert_eq!(values.nodeplugin.volume_mounts, vec![]);
    }

    #[test]
    fn test_get_manifests() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster.clone());
        addon.manifests().expect("failed to get manifests");
    }
}
