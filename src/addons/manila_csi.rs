use crate::{
    addons::{csi::CSIComponent, ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum::{self, ClusterError},
};
use docker_image::DockerImage;
use include_dir::{include_dir, Dir};
use k8s_openapi::api::core::v1::Toleration;
use maplit::btreemap;
use serde::{Deserialize, Serialize};
use serde_yaml::Value;
use std::collections::BTreeMap;

static NFS_CSI_MANIFESTS: Dir<'_> = include_dir!("magnum_cluster_api/manifests/nfs-csi");

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
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CSIControllerPlugin {
    provisioner: CSIComponent,
    snapshotter: CSIComponent,
    resizer: CSIComponent,
    tolerations: Vec<Toleration>,
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
            },
        })
    }
}

pub struct Addon {
    cluster: magnum::Cluster,
}

impl Addon {}

fn mapping_get_mut<'a>(value: &'a mut Value, key: &str) -> Option<&'a mut Value> {
    value
        .as_mapping_mut()?
        .get_mut(Value::String(key.to_owned()))
}

fn mirror_nfs_csi_image(image: &str, registry: &Option<String>) -> String {
    let Some(registry) = registry else {
        return image.to_owned();
    };

    let Some(name) = image.strip_prefix("registry.k8s.io/sig-storage/") else {
        return image.to_owned();
    };

    let name = match name.strip_prefix("livenessprobe:") {
        Some(tag) => format!("csi-livenessprobe:{tag}"),
        None => name.to_owned(),
    };

    format!("{}/{}", registry.trim_end_matches('/'), name)
}

fn rewrite_workload_images(doc: &mut Value, registry: &Option<String>) {
    let kind = doc
        .as_mapping()
        .and_then(|mapping| mapping.get(Value::String("kind".to_owned())))
        .and_then(Value::as_str);

    if !matches!(kind, Some("DaemonSet" | "Deployment" | "StatefulSet")) {
        return;
    }

    let Some(spec) = mapping_get_mut(doc, "spec")
        .and_then(|value| mapping_get_mut(value, "template"))
        .and_then(|value| mapping_get_mut(value, "spec"))
    else {
        return;
    };

    for key in ["initContainers", "containers"] {
        let Some(Value::Sequence(containers)) = mapping_get_mut(spec, key) else {
            continue;
        };

        for container in containers {
            let Some(Value::String(image)) = mapping_get_mut(container, "image") else {
                continue;
            };

            *image = mirror_nfs_csi_image(image, registry);
        }
    }
}

fn render_nfs_csi_manifest(
    manifest: &str,
    registry: &Option<String>,
) -> Result<String, helm::HelmTemplateError> {
    let mut docs = serde_yaml::Deserializer::from_str(manifest)
        .map(Value::deserialize)
        .collect::<Result<Vec<_>, _>>()?;

    for doc in &mut docs {
        rewrite_workload_images(doc, registry);
    }

    let docs = docs
        .into_iter()
        .map(|doc| serde_yaml::to_string(&doc))
        .collect::<Result<Vec<_>, _>>()?;

    Ok(docs.join("---\n"))
}

impl ClusterAddon for Addon {
    fn new(cluster: magnum::Cluster) -> Self {
        Self { cluster }
    }

    fn enabled(&self) -> bool {
        self.cluster.labels.manila_csi_enabled
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-manila-csi", self.cluster.stack_id()?))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        let values = &CSIValues::try_from(self.cluster.clone()).expect("failed to create values");

        let mut manifests = btreemap! {
            "manila-csi.yaml".to_owned() => helm::template_using_include_dir(
                include_dir!("magnum_cluster_api/charts/openstack-manila-csi"),
                "manila-csi",
                "kube-system",
                values,
            )?,
        };

        for file in NFS_CSI_MANIFESTS.files() {
            let Some(filename) = file.path().file_name().and_then(|name| name.to_str()) else {
                continue;
            };

            let Some(contents) = file.contents_utf8() else {
                continue;
            };

            manifests.insert(
                filename.to_owned(),
                render_nfs_csi_manifest(contents, &self.cluster.labels.container_infra_prefix)?,
            );
        }

        Ok(manifests)
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

    #[test]
    fn test_get_manifests_includes_nfs_csi_dependency() {
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
        let manifests = addon.manifests().expect("failed to get manifests");

        assert!(manifests.contains_key("manila-csi.yaml"));
        assert!(manifests.contains_key("csi-nfs-controller.yaml"));
        assert!(manifests.contains_key("csi-nfs-driverinfo.yaml"));
        assert!(manifests.contains_key("csi-nfs-node.yaml"));
        assert!(manifests.contains_key("rbac-csi-nfs.yaml"));
        assert!(
            manifests["csi-nfs-node.yaml"].contains("registry.k8s.io/sig-storage/nfsplugin:v4.2.0")
        );
    }

    #[test]
    fn test_get_manifests_mirrors_nfs_csi_images() {
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

        let addon = Addon::new(cluster.clone());
        let manifests = addon.manifests().expect("failed to get manifests");

        assert!(manifests["csi-nfs-node.yaml"].contains("registry.example.com/nfsplugin:v4.2.0"));
        assert!(manifests["csi-nfs-node.yaml"]
            .contains("registry.example.com/csi-livenessprobe:v2.8.0"));
        assert!(manifests["csi-nfs-node.yaml"]
            .contains("registry.example.com/csi-node-driver-registrar:v2.6.2"));
        assert!(manifests["csi-nfs-controller.yaml"]
            .contains("registry.example.com/csi-provisioner:v3.3.0"));
    }
}
