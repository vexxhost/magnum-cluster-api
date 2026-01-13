use crate::{
    addons::{cinder_csi, manila_csi, ClusterAddon, ClusterAddonValues, ClusterAddonValuesError, ImageDetails},
    magnum::{self, ClusterError},
};
use docker_image::DockerImage;
use include_dir::include_dir;
use maplit::btreemap;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Values we pass to the helm chart
#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct SnapshotControllerValues {
    controller: ControllerValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct ControllerValues {
    #[serde(rename = "fullnameOverride")]
    fullname_override: String,

    image: ImageDetails,

    #[serde(rename = "volumeSnapshotClasses")]
    volume_snapshot_classes: Vec<VolumeSnapshotClass>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct VolumeSnapshotClass {
    name: String,

    #[serde(skip_serializing_if = "Option::is_none")]
    annotations: Option<BTreeMap<String, String>>,

    driver: String,

    #[serde(rename = "deletionPolicy")]
    deletion_policy: String,

    #[serde(skip_serializing_if = "Option::is_none")]
    parameters: Option<BTreeMap<String, String>>,
}

/// Values from the chart's values.yaml for defaults lookup
#[derive(Debug, Deserialize)]
struct ChartDefaultValues {
    controller: ChartControllerDefaults,
}

#[derive(Debug, Deserialize)]
struct ChartControllerDefaults {
    image: ImageDetails,
}

impl ClusterAddonValues for SnapshotControllerValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        // We don't load full defaults from values.yaml for this addon since we
        // construct values programmatically based on enabled CSI drivers
        Ok(Self {
            controller: ControllerValues {
                fullname_override: "snapshot-controller".to_string(),
                image: ImageDetails::default(),
                volume_snapshot_classes: vec![],
            },
        })
    }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => {
                // When using a custom registry, the image is named 'csi-snapshot-controller'
                format!("{}/csi-snapshot-controller", registry.trim_end_matches('/'))
            }
            None => image.to_string(),
        }
    }
}

impl SnapshotControllerValues {
    fn get_chart_defaults() -> Result<ChartDefaultValues, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/snapshot-controller/values.yaml"
        ));
        let values: ChartDefaultValues = serde_yaml::from_str(file)?;
        Ok(values)
    }
}

impl TryFrom<magnum::Cluster> for SnapshotControllerValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let chart_defaults = Self::get_chart_defaults()?;

        // Build volume snapshot classes based on enabled CSI drivers
        let mut volume_snapshot_classes = Vec::new();

        // Add Cinder CSI volume snapshot class if enabled
        let cinder_addon = cinder_csi::Addon::new(cluster.clone());
        if cinder_addon.enabled() {
            volume_snapshot_classes.push(VolumeSnapshotClass {
                name: "block-snapshot".to_string(),
                annotations: Some(btreemap! {
                    "snapshot.storage.kubernetes.io/is-default-class".to_string() => "true".to_string(),
                }),
                driver: "cinder.csi.openstack.org".to_string(),
                deletion_policy: "Delete".to_string(),
                parameters: None,
            });
        }

        // Add Manila CSI volume snapshot class if enabled and share_network_id is specified
        let manila_addon = manila_csi::Addon::new(cluster.clone());
        if manila_addon.enabled() && cluster.labels.manila_csi_share_network_id.is_some() {
            volume_snapshot_classes.push(VolumeSnapshotClass {
                name: "share-snapshot".to_string(),
                annotations: Some(btreemap! {
                    "snapshot.storage.kubernetes.io/is-default-class".to_string() => "true".to_string(),
                }),
                driver: "nfs.manila.csi.openstack.org".to_string(),
                deletion_policy: "Delete".to_string(),
                parameters: Some(btreemap! {
                    "csi.storage.k8s.io/snapshotter-secret-name".to_string() => "csi-manila-secrets".to_string(),
                    "csi.storage.k8s.io/snapshotter-secret-namespace".to_string() => "kube-system".to_string(),
                }),
            });
        }

        Ok(Self {
            controller: ControllerValues {
                fullname_override: "snapshot-controller".to_string(),
                image: chart_defaults
                    .controller
                    .image
                    .using_cluster::<Self>(&cluster, &cluster.labels.csi_snapshot_controller_tag)?,
                volume_snapshot_classes,
            },
        })
    }
}

pub struct Addon {
    cluster: magnum::Cluster,
}

impl ClusterAddon for Addon {
    fn new(cluster: magnum::Cluster) -> Self {
        Self { cluster }
    }

    fn enabled(&self) -> bool {
        // Snapshot controller is enabled if either Cinder CSI or Manila CSI is enabled
        let cinder_addon = cinder_csi::Addon::new(self.cluster.clone());
        let manila_addon = manila_csi::Addon::new(self.cluster.clone());
        cinder_addon.enabled() || manila_addon.enabled()
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-snapshot-controller", self.cluster.stack_id()?))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        let values =
            &SnapshotControllerValues::try_from(self.cluster.clone()).expect("failed to create values");

        Ok(btreemap! {
            "snapshot-controller.yaml".to_owned() => helm::template_using_include_dir_with_options(
                include_dir!("magnum_cluster_api/charts/snapshot-controller"),
                "snapshot-controller",
                "kube-system",
                values,
                helm::TemplateOptions { include_crds: true },
            )?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_snapshot_controller_enabled_with_cinder_csi() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        assert!(addon.enabled());
    }

    #[test]
    fn test_snapshot_controller_enabled_with_manila_csi() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(false)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        assert!(addon.enabled());
    }

    #[test]
    fn test_snapshot_controller_enabled_with_both_csi() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        assert!(addon.enabled());
    }

    #[test]
    fn test_snapshot_controller_disabled_without_csi() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(false)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        assert!(!addon.enabled());
    }

    #[test]
    fn test_snapshot_controller_values_with_cinder_only() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: SnapshotControllerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.controller.fullname_override, "snapshot-controller");
        assert_eq!(values.controller.volume_snapshot_classes.len(), 1);
        assert_eq!(
            values.controller.volume_snapshot_classes[0].name,
            "block-snapshot"
        );
        assert_eq!(
            values.controller.volume_snapshot_classes[0].driver,
            "cinder.csi.openstack.org"
        );
    }

    #[test]
    fn test_snapshot_controller_values_with_manila_only() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(false)
                .manila_csi_enabled(true)
                .manila_csi_share_network_id(Some("share-net-123".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: SnapshotControllerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.controller.volume_snapshot_classes.len(), 1);
        assert_eq!(
            values.controller.volume_snapshot_classes[0].name,
            "share-snapshot"
        );
        assert_eq!(
            values.controller.volume_snapshot_classes[0].driver,
            "nfs.manila.csi.openstack.org"
        );
        assert!(values.controller.volume_snapshot_classes[0]
            .parameters
            .is_some());
    }

    #[test]
    fn test_snapshot_controller_values_with_manila_without_share_network_id() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(false)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: SnapshotControllerValues =
            cluster.clone().try_into().expect("failed to create values");

        // No volume snapshot classes when share_network_id is not specified
        assert_eq!(values.controller.volume_snapshot_classes.len(), 0);
    }

    #[test]
    fn test_snapshot_controller_values_with_both_csi() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .manila_csi_enabled(true)
                .manila_csi_share_network_id(Some("share-net-123".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: SnapshotControllerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.controller.volume_snapshot_classes.len(), 2);
        assert_eq!(
            values.controller.volume_snapshot_classes[0].name,
            "block-snapshot"
        );
        assert_eq!(
            values.controller.volume_snapshot_classes[1].name,
            "share-snapshot"
        );
    }

    #[test]
    fn test_snapshot_controller_values_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: SnapshotControllerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.controller.image.repository,
            "registry.example.com/csi-snapshot-controller"
        );
    }

    #[test]
    fn test_snapshot_controller_values_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: SnapshotControllerValues =
            cluster.clone().try_into().expect("failed to create values");

        // Default repository from chart values.yaml
        assert_eq!(
            values.controller.image.repository,
            "registry.k8s.io/sig-storage/snapshot-controller"
        );
    }

    #[test]
    fn test_get_manifests() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        let manifests = addon.manifests().expect("failed to get manifests");
        assert!(manifests.contains_key("snapshot-controller.yaml"));
    }

    #[test]
    fn test_secret_name() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        assert_eq!(
            addon.secret_name().unwrap(),
            "kube-abcde-snapshot-controller"
        );
    }
}
