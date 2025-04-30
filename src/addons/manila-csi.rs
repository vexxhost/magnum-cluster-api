use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum,
};
use docker_image::DockerImage;
use include_dir::include_dir;
use k8s_openapi::api::core::v1::Toleration;
use serde::{Deserialize, Serialize};
use typed_builder::TypedBuilder;

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct ManilaCsiValues {
    csimanila: ImageWrapper,
    nodeplugin: NodePluginWrapper,
    controllerplugin: ControllerPluginWrapper,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct ImageWrapper {
    image: ImageDetails,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct NodePluginWrapper {
    registrar: ImageWrapper,
    tolerations: Vec<Toleration>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct ControllerPluginWrapper {
    provisioner: ImageWrapper,
    snapshotter: ImageWrapper,
    resizer: ImageWrapper,
    tolerations: Vec<Toleration>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct ImageDetails {
    repository: String,
    tag: String,
    #[serde(rename = "pullPolicy")]
    pull_policy: String,
}

impl ClusterAddonValues for ManilaCsiValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/openstack-manila-csi/values.yaml"
        ));
        let values: ManilaCsiValues = serde_yaml::from_str(file)?;

        Ok(values)
    }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => format!("{}/{}", registry.trim_end_matches('/'), image.name.split('/').next_back().unwrap()),
            None => image.to_string(),
        }
    }
}

impl TryFrom<magnum::Cluster> for ManilaCsiValues {
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

        update_image!(values.csimanila.image);
        update_image!(values.nodeplugin.registrar.image);
        update_image!(values.controllerplugin.provisioner.image);
        update_image!(values.controllerplugin.snapshotter.image);
        update_image!(values.controllerplugin.resizer.image);

        // Set tolerations
        values.nodeplugin.tolerations = vec![
            Toleration {
                operator: Some("Exists".to_string()),
                ..Default::default()
            },
        ];

        values.controllerplugin.tolerations = vec![
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
        let values = &ManilaCsiValues::try_from(self.cluster.clone())
            .expect("failed to create values");
        helm::template_using_include_dir(
            include_dir!("magnum_cluster_api/charts/openstack-manila-csi"),
            "manila-csi",
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
    fn test_manila_csi_values_for_cluster_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            status: magnum::ClusterStatus::CreateInProgress,
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: ManilaCsiValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.nodeplugin.tolerations.len(), 1);
        assert_eq!(values.controllerplugin.tolerations.len(), 2);
    }

    #[test]
    fn test_manila_csi_values_for_cluster_with_custom_registry() {
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

        let values: ManilaCsiValues =
            cluster.clone().try_into().expect("failed to create values");

        assert!(values.csimanila.image.repository.starts_with("registry.example.com/"));
        assert!(values.nodeplugin.registrar.image.repository.starts_with("registry.example.com/"));
        assert!(values.controllerplugin.provisioner.image.repository.starts_with("registry.example.com/"));
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
