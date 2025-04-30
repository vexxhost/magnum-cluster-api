use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum,
};
use docker_image::DockerImage;
use include_dir::include_dir;
use k8s_openapi::api::core::v1::{Toleration, Volume, VolumeMount};
use serde::{Deserialize, Serialize};
use typed_builder::TypedBuilder;

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct CinderCsiValues {
    csi: CsiComponents,
    secret: CinderCsiSecretValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct CsiComponents {
    attacher: CsiImage,
    provisioner: CsiImage,
    snapshotter: CsiImage,
    resizer: CsiImage,
    livenessprobe: CsiImage,
    #[serde(rename = "nodeDriverRegistrar")]
    node_driver_registrar: CsiImage,
    plugin: CsiPlugin,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct CsiImage {
    image: ImageDetails,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct ImageDetails {
    repository: String,
    tag: String,
    #[serde(rename = "pullPolicy")]
    pull_policy: String,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct CsiPlugin {
    image: ImageDetails,
    #[serde(rename = "controllerPlugin")]
    controller_plugin: CsiPluginTolerations,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct CsiPluginTolerations {
    tolerations: Vec<Toleration>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct CinderCsiSecretValues {
    enabled: bool,
    #[serde(rename = "hostMount")]
    host_mount: bool,
    create: bool,
    filename: String,
    name: String,
}

impl ClusterAddonValues for CinderCsiValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/openstack-cinder-csi/values.yaml"
        ));
        let values: CinderCsiValues = serde_yaml::from_str(file)?;

        Ok(values)
    }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => format!("{}/{}", registry.trim_end_matches('/'), image.name.split('/').next_back().unwrap()),
            None => image.to_string(),
        }
    }
}

impl TryFrom<magnum::Cluster> for CinderCsiValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let mut values = Self::defaults()?;

        let prefix = &cluster.labels.container_infra_prefix;

        macro_rules! update_image {
            ($component:expr) => {
                {
                    let image = DockerImage::parse(&$component.image.repository)?;
                    $component.image.repository = Self::get_mirrored_image_name(image, prefix);
                }
            };
        }

        update_image!(values.csi.attacher);
        update_image!(values.csi.provisioner);
        update_image!(values.csi.snapshotter);
        update_image!(values.csi.resizer);
        update_image!(values.csi.livenessprobe);
        update_image!(values.csi.node_driver_registrar);
        update_image!(values.csi.plugin);

        // Set tolerations
        let tolerations = vec![
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
        ];

        values.csi.plugin.controller_plugin.tolerations = tolerations;

        // Set secret
        values.secret.enabled = true;
        values.secret.name = "cloud-config".to_string();

        Ok(values)
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
        true
    }

    fn manifests(&self) -> Result<String, helm::HelmTemplateError> {
        let values = &CinderCsiValues::try_from(self.cluster.clone())
            .expect("failed to create values");
        helm::template_using_include_dir(
            include_dir!("magnum_cluster_api/charts/openstack-cinder-csi"),
            "cinder-csi",
            "kube-system",
            values,
        )
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
            status: magnum::ClusterStatus::CreateInProgress,
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CinderCsiValues =
            cluster.clone().try_into().expect("failed to create values");

        assert!(values.secret.enabled);
        assert_eq!(values.secret.name, "cloud-config");
        assert_eq!(values.csi.plugin.controller_plugin.tolerations.len(), 2);
    }

    #[test]
    fn test_cinder_csi_values_for_cluster_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            status: magnum::ClusterStatus::CreateInProgress,
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CinderCsiValues =
            cluster.clone().try_into().expect("failed to create values");

        assert!(values.csi.attacher.image.repository.starts_with("registry.example.com/"));
        assert!(values.csi.plugin.image.repository.starts_with("registry.example.com/"));
    }

    #[test]
    fn test_get_manifests() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            status: magnum::ClusterStatus::CreateInProgress,
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
