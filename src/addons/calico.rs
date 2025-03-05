use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum,
};
use docker_image::DockerImage;
use serde::{Deserialize, Serialize};
use std::{fs::File, path::PathBuf};

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CalicoValues {
    installation: CalicoInstallationValues,

    #[serde(rename = "tigeraOperator")]
    tigera_operator: CalicoTigeraOperatorValues,

    calicoctl: CalicoCalicoCtlValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CalicoInstallationValues {
    /// Image format:
    /// `<registry><imagePath>/<imagePrefix><imageName>:<image-tag>`
    /// This option allows configuring the `<registry>` portion of the above format.
    registry: Option<String>,

    /// Image format:
    /// `<registry><imagePath>/<imagePrefix><imageName>:<image-tag>`
    /// This option allows configuring the `<imagePath>` portion of the above format.
    #[serde(rename = "imagePath")]
    image_path: Option<String>,

    /// Image format:
    /// `<registry><imagePath>/<imagePrefix><imageName>:<image-tag>`
    /// This option allows configuring the `<imagePrefix>` portion of the above format.
    #[serde(rename = "imagePrefix")]
    image_prefix: Option<String>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CalicoTigeraOperatorValues {
    registry: String,
    image: String,
    version: String,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CalicoCalicoCtlValues {
    image: String,
    tag: String,
}

impl TryFrom<magnum::Cluster> for CalicoValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let mut values = Self::defaults()?;

        values.calicoctl.image = Self::get_mirrored_image_name(
            DockerImage::parse(&values.calicoctl.image)?,
            &cluster.labels.container_infra_prefix,
        );
        values.calicoctl.tag = cluster.labels.calico_tag;

        if cluster.labels.container_infra_prefix.is_some() {
            let container_infra_prefix = cluster.labels.container_infra_prefix.unwrap().to_string();

            values.installation.registry = Some(container_infra_prefix.clone());
            values.installation.image_path = Some("".to_owned());
            values.installation.image_prefix = Some("calico-".to_string());

            values.tigera_operator.registry = container_infra_prefix.clone();
            values.tigera_operator.image = "tigera-operator".to_owned();
        } else {
            values.installation.registry = Some("quay.io".to_string());
        }

        Ok(values)
    }
}

impl ClusterAddonValues for CalicoValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = File::open("magnum_cluster_api/charts/tigera-operator/values.yaml")?;
        let values: CalicoValues = serde_yaml::from_reader(file)?;

        Ok(values)
    }

    fn get_images() -> Result<Vec<DockerImage>, ClusterAddonValuesError> {
        let values = Self::defaults()?;

        Ok(vec![
            DockerImage::parse(&values.calicoctl.image)?,
            DockerImage::parse(&values.tigera_operator.image)?,
        ])
    }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => {
                format!("{}/{}", registry, image.name.replace("calico/", "calico-"))
            }
            None => {
                if image.registry == Some("docker.io".to_string()) {
                    format!("quay.io/{}", image.name)
                } else {
                    image.to_string()
                }
            }
        }
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
        self.cluster.cluster_template.network_driver == "calico"
    }

    fn manifests<T: ClusterAddonValues + Serialize>(
        &self,
        values: &T,
    ) -> Result<Vec<serde_yaml::Value>, helm::HelmTemplateError> {
        Ok(helm::template(
            &PathBuf::from("magnum_cluster_api/charts/calico"),
            "calico",
            "tigera-operator",
            values,
        )?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_calico_values_try_from_cluster_without_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CalicoValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values,
            CalicoValues {
                installation: CalicoInstallationValues {
                    registry: Some("quay.io".to_string()),
                    image_path: Some("calico-".to_string()),
                    image_prefix: None,
                },
                tigera_operator: CalicoTigeraOperatorValues {
                    registry: "quay.io".to_string(),
                    image: "tigera/operator".to_string(),
                    version: "v1.36.5".to_string(),
                },
                calicoctl: CalicoCalicoCtlValues {
                    image: "quay.io/calico/ctl".to_string(),
                    tag: "v3.29.2".to_string(),
                },
            }
        );
    }

    #[test]
    fn test_calico_values_try_from_cluster_with_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CalicoValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values,
            CalicoValues {
                installation: CalicoInstallationValues {
                    registry: Some("registry.example.com".to_string()),
                    image_path: Some("".to_string()),
                    image_prefix: None,
                },
                tigera_operator: CalicoTigeraOperatorValues {
                    registry: "registry.example.com".to_string(),
                    image: "tigera-operator".to_string(),
                    version: "v1.36.5".to_string(),
                },
                calicoctl: CalicoCalicoCtlValues {
                    image: "registry.example.com/calico-ctl".to_string(),
                    tag: "v3.29.2".to_string(),
                },
            }
        );
    }

    #[test]
    fn test_get_manifests() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let addon = Addon::new(cluster.clone());
        let values: CalicoValues = cluster.clone().try_into().expect("failed to create values");
        let manifests = addon.manifests(&values).expect("failed to get manifests");

        assert_eq!(manifests.len(), 14);
    }
}
