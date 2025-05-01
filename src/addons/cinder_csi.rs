use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError, ImageDetails},
    magnum::{self, ClusterError},
};
use docker_image::DockerImage;
use include_dir::include_dir;
use k8s_openapi::api::core::v1::{Toleration, Volume, VolumeMount};
use maplit::btreemap;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIValues {
    csi: CSIComponents,
    secret: CSISecret,

    #[serde(rename = "storageClass")]
    storage_class: CSIStorageClass,

    #[serde(rename = "clusterID")]
    cluster_id: String,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIComponents {
    attacher: CSIComponent,
    provisioner: CSIComponent,
    snapshotter: CSIComponent,
    resizer: CSIComponent,
    livenessprobe: CSIComponent,

    #[serde(rename = "nodeDriverRegistrar")]
    node_driver_registrar: CSIComponent,

    plugin: CSIPlugin,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CSIComponent {
    image: ImageDetails,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIControllerPlugin {
    tolerations: Vec<Toleration>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIPlugin {
    image: ImageDetails,
    volumes: Vec<Volume>,

    #[serde(rename = "volumeMounts")]
    volume_mounts: Vec<VolumeMount>,

    #[serde(rename = "controllerPlugin")]
    controller_plugin: CSIControllerPlugin,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSISecret {
    enabled: bool,
    name: Option<String>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIStorageClass {
    enabled: bool,
}

impl ClusterAddonValues for CSIValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/openstack-cinder-csi/values.yaml"
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
            csi: CSIComponents {
                attacher: CSIComponent {
                    image: values
                        .csi
                        .attacher
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_attacher_tag)?,
                },
                provisioner: CSIComponent {
                    image: values
                        .csi
                        .provisioner
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_provisioner_tag)?,
                },
                snapshotter: CSIComponent {
                    image: values
                        .csi
                        .snapshotter
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_snapshotter_tag)?,
                },
                resizer: CSIComponent {
                    image: values
                        .csi
                        .resizer
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_resizer_tag)?,
                },
                livenessprobe: CSIComponent {
                    image: values
                        .csi
                        .livenessprobe
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.csi_liveness_probe_tag)?,
                },
                node_driver_registrar: CSIComponent {
                    image: values
                        .csi
                        .node_driver_registrar
                        .image
                        .using_cluster::<Self>(
                            &cluster,
                            &cluster.labels.csi_node_driver_registrar_tag,
                        )?,
                },
                plugin: CSIPlugin {
                    image: values
                        .csi
                        .plugin
                        .image
                        .using_cluster::<Self>(&cluster, &cluster.labels.cinder_csi_plugin_tag)?,
                    volumes: vec![],
                    volume_mounts: vec![
                        VolumeMount {
                            name: "cloud-config".into(),
                            mount_path: "/etc/kubernetes".into(),
                            read_only: Some(true),
                            ..Default::default()
                        },
                        VolumeMount {
                            name: "cloud-config".into(),
                            mount_path: "/etc/config".into(),
                            read_only: Some(true),
                            ..Default::default()
                        },
                    ],
                    controller_plugin: CSIControllerPlugin {
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
                    },
                },
            },
            secret: CSISecret {
                enabled: true,
                name: Some("cloud-config".into()),
            },
            storage_class: CSIStorageClass { enabled: false },
            cluster_id: cluster.uuid.clone(),
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
        self.cluster.labels.cinder_csi_enabled
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-cinder-csi", self.cluster.stack_id()?))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        let values = &CSIValues::try_from(self.cluster.clone()).expect("failed to create values");

        Ok(btreemap! {
            "cinder-csi.yaml".to_owned() => helm::template_using_include_dir(
                include_dir!("magnum_cluster_api/charts/openstack-cinder-csi"),
                "cinder-csi",
                "kube-system",
                values,
            )?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_cinder_csi_values_for_cluster_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CSIValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.csi.attacher.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-attacher".into(),
                tag: cluster.labels.csi_attacher_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.csi.provisioner.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-provisioner".into(),
                tag: cluster.labels.csi_provisioner_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.csi.snapshotter.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-snapshotter".into(),
                tag: cluster.labels.csi_snapshotter_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.csi.resizer.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-resizer".into(),
                tag: cluster.labels.csi_resizer_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.csi.livenessprobe.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/livenessprobe".into(),
                tag: cluster.labels.csi_liveness_probe_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.csi.node_driver_registrar.image,
            ImageDetails {
                repository: "registry.k8s.io/sig-storage/csi-node-driver-registrar".into(),
                tag: cluster.labels.csi_node_driver_registrar_tag,
                use_digest: Some(true),
            }
        );
        assert_eq!(
            values.csi.plugin.image,
            ImageDetails {
                repository: "registry.k8s.io/provider-os/cinder-csi-plugin".into(),
                tag: cluster.labels.cinder_csi_plugin_tag,
                use_digest: Some(true),
            }
        );
    }

    #[test]
    fn test_cinder_csi_values_for_cluster_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CSIValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.csi.attacher.image,
            ImageDetails {
                repository: "registry.example.com/csi-attacher".into(),
                tag: cluster.labels.csi_attacher_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.csi.provisioner.image,
            ImageDetails {
                repository: "registry.example.com/csi-provisioner".into(),
                tag: cluster.labels.csi_provisioner_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.csi.snapshotter.image,
            ImageDetails {
                repository: "registry.example.com/csi-snapshotter".into(),
                tag: cluster.labels.csi_snapshotter_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.csi.resizer.image,
            ImageDetails {
                repository: "registry.example.com/csi-resizer".into(),
                tag: cluster.labels.csi_resizer_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.csi.livenessprobe.image,
            ImageDetails {
                repository: "registry.example.com/livenessprobe".into(),
                tag: cluster.labels.csi_liveness_probe_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.csi.node_driver_registrar.image,
            ImageDetails {
                repository: "registry.example.com/csi-node-driver-registrar".into(),
                tag: cluster.labels.csi_node_driver_registrar_tag,
                use_digest: Some(false),
            }
        );
        assert_eq!(
            values.csi.plugin.image,
            ImageDetails {
                repository: "registry.example.com/cinder-csi-plugin".into(),
                tag: cluster.labels.cinder_csi_plugin_tag,
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
        };

        let values: CSIValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.csi.plugin.volumes, vec![]);
        assert_eq!(
            values.csi.plugin.volume_mounts,
            vec![
                VolumeMount {
                    name: "cloud-config".into(),
                    mount_path: "/etc/kubernetes".into(),
                    read_only: Some(true),
                    ..Default::default()
                },
                VolumeMount {
                    name: "cloud-config".into(),
                    mount_path: "/etc/config".into(),
                    read_only: Some(true),
                    ..Default::default()
                },
            ]
        );
        assert_eq!(
            values.csi.plugin.controller_plugin.tolerations,
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
            values.secret,
            CSISecret {
                enabled: true,
                name: Some("cloud-config".into())
            }
        );
        assert_eq!(values.storage_class.enabled, false);
        assert_eq!(values.cluster_id, cluster.uuid);
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
        };

        let addon = Addon::new(cluster.clone());
        addon.manifests().expect("failed to get manifests");
    }
}
