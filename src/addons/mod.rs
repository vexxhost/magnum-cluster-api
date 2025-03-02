use docker_image::DockerImage;
use thiserror::Error;

use crate::magnum;

pub mod cilium;

trait ClusterAddon {
    fn new(cluster: magnum::Cluster) -> Result<Self, AddonError> where Self: Sized;
    fn enabled(&self) -> bool;
    fn resolve_image(&self, image: &DockerImage) -> String;
    fn manifests(&self) -> Vec<serde_yaml::Value>;
}

#[derive(Debug, Error)]
pub enum AddonError {
    #[error("failed to read values.yaml file: {0}")]
    IoError(#[from] std::io::Error),

    #[error("failed to parse values.yaml file: {0}")]
    SerdeError(#[from] serde_yaml::Error),
}
