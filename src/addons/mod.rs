use crate::magnum::{self, ClusterError};
use docker_image::DockerImage;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use thiserror::Error;

pub mod cilium;
pub mod cinder_csi;
pub mod cloud_controller_manager;
pub mod manila_csi;

#[cfg_attr(test, mockall::automock)]
pub trait ClusterAddon {
    fn new(cluster: magnum::Cluster) -> Self;
    fn enabled(&self) -> bool;
    fn secret_name(&self) -> Result<String, ClusterError>;
    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError>;
}

pub trait ClusterAddonValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError>
    where
        Self: Sized;
    // fn get_images() -> Result<Vec<DockerImage>, ClusterAddonValuesError>;
    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String;
}

#[derive(Debug, Error)]
pub enum ClusterAddonValuesError {
    #[error("failed to read values.yaml file: {0}")]
    Io(#[from] std::io::Error),

    #[error("failed to parse values.yaml file: {0}")]
    Serde(#[from] serde_yaml::Error),

    #[error("failed to parse docker reference: {0}")]
    DockerReference(#[from] docker_image::DockerImageError),
}

#[derive(Debug, Default, Deserialize, PartialEq, Serialize)]
pub struct ImageDetails {
    repository: String,
    tag: String,

    #[serde(rename = "useDigest")]
    use_digest: Option<bool>,
}

impl ImageDetails {
    pub fn using_cluster<T: ClusterAddonValues>(
        &self,
        cluster: &magnum::Cluster,
        tag: &str,
    ) -> Result<Self, ClusterAddonValuesError> {
        let image = DockerImage::parse(self.repository.as_str())?;
        let repository = T::get_mirrored_image_name(image, &cluster.labels.container_infra_prefix);

        Ok(Self {
            repository,
            tag: tag.to_owned(),
            use_digest: Some(cluster.labels.container_infra_prefix.is_none()),
        })
    }
}
