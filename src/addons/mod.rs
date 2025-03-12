use crate::magnum;
use docker_image::DockerImage;
use serde::Serialize;
use thiserror::Error;

pub mod cilium;
pub mod cloud_controller_manager;

pub trait ClusterAddon {
    fn new(cluster: magnum::Cluster) -> Self;
    fn enabled(&self) -> bool;
    fn manifests<T: ClusterAddonValues + Serialize>(
        &self,
        values: &T,
    ) -> Result<String, helm::HelmTemplateError>;
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
