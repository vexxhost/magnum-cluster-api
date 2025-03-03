use crate::magnum;
use docker_image::DockerImage;
use serde::Serialize;
use thiserror::Error;

pub mod calico;
pub mod cilium;

trait ClusterAddon {
    fn new(cluster: magnum::Cluster) -> Self;
    fn enabled(&self) -> bool;
    fn manifests<T: ClusterAddonValues + Serialize>(
        &self,
        values: &T,
    ) -> Result<Vec<serde_yaml::Value>, helm::HelmTemplateError>;
}

trait ClusterAddonValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError>
    where
        Self: Sized;
    fn get_images() -> Result<Vec<DockerImage>, ClusterAddonValuesError>;
    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String;
}

#[derive(Debug, Error)]
pub enum ClusterAddonValuesError {
    #[error("failed to read values.yaml file: {0}")]
    IoError(#[from] std::io::Error),

    #[error("failed to parse values.yaml file: {0}")]
    SerdeError(#[from] serde_yaml::Error),

    #[error("failed to parse docker reference: {0}")]
    DockerReferenceError(#[from] docker_image::DockerImageError),
}
