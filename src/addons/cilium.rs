use crate::{
    addons::{AddonError, ClusterAddon},
    magnum,
};
use docker_image::DockerImage;
use serde::Deserialize;
use std::fs::File;

#[derive(Deserialize)]
struct CiliumValues {
    image: CiliumImageValues,
    certgen: CiliumCertGenValues,
    hubble: CiliumHubbleValues,
    envoy: CiliumEnvoyValues,
    etcd: CiliumEtcdValues,
    operator: CiliumOperatorValues,
    nodeinit: CiliumNodeInitValues,
    preflight: CiliumPreflightValues,
    clustermesh: CiliumClustermeshValues,
}

#[derive(Deserialize)]
struct CiliumImageValues {
    repository: String,
}

#[derive(Deserialize)]
struct CiliumCertGenValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumHubbleValues {
    relay: CiliumHubbleRelayValues,
    ui: CiliumHubbleUiValues,
}

#[derive(Deserialize)]
struct CiliumHubbleRelayValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumHubbleUiValues {
    backend: CiliumHubbleUiBackendValues,
    frontend: CiliumHubbleUiFrontendValues,
}

#[derive(Deserialize)]
struct CiliumHubbleUiBackendValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumHubbleUiFrontendValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumEnvoyValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumEtcdValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumOperatorValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumNodeInitValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumPreflightValues {
    image: CiliumImageValues,
}

#[derive(Deserialize)]
struct CiliumClustermeshValues {
    apiserver: CiliumClustermeshApiserverValues,
}

#[derive(Deserialize)]
struct CiliumClustermeshApiserverValues {
    image: CiliumImageValues,
}

impl CiliumValues {
    pub fn new() -> Result<Self, AddonError> {
        let file = File::open("magnum_cluster_api/charts/cilium/values.yaml")?;
        Ok(serde_yaml::from_reader(file)?)
    }
}

pub struct Addon {
    cluster: magnum::Cluster,
    chart_values: CiliumValues,
}

impl Addon {}

impl ClusterAddon for Addon {
    fn new(cluster: magnum::Cluster) -> Result<Self, AddonError> {
        Ok(Self {
            cluster,
            chart_values: CiliumValues::new()?,
        })
    }

    fn enabled(&self) -> bool {
        todo!()
    }

    fn resolve_image(&self, image: &DockerImage) -> String {
        match self.cluster.labels.container_infra_prefix {
            Some(ref container_infra_prefix) => {
                format!(
                    "{}/{}",
                    container_infra_prefix,
                    image.name.replace("cilium/", "cilium-")
                )
            }
            None => image.to_string(),
        }
    }

    fn manifests(&self) -> Vec<serde_yaml::Value> {
        let values = CiliumValues {
            image: CiliumImageValues {
                repository: self.chart_values.image.repository.clone(),
            },
            certgen: CiliumCertGenValues {
                image: CiliumImageValues {
                    repository: self.chart_values.certgen.image.repository.clone(),
                },
            },
            hubble: CiliumHubbleValues {
                relay: CiliumHubbleRelayValues {
                    image: CiliumImageValues {
                        repository: self.chart_values.hubble.relay.image.repository.clone(),
                    },
                },
                ui: CiliumHubbleUiValues {
                    backend: CiliumHubbleUiBackendValues {
                        image: CiliumImageValues {
                            repository: self
                                .chart_values
                                .hubble
                                .ui
                                .backend
                                .image
                                .repository
                                .clone(),
                        },
                    },
                    frontend: CiliumHubbleUiFrontendValues {
                        image: CiliumImageValues {
                            repository: self
                                .chart_values
                                .hubble
                                .ui
                                .frontend
                                .image
                                .repository
                                .clone(),
                        },
                    },
                },
            },
            envoy: CiliumEnvoyValues {
                image: CiliumImageValues {
                    repository: self.chart_values.envoy.image.repository.clone(),
                },
            },
            etcd: CiliumEtcdValues {
                image: CiliumImageValues {
                    repository: self.chart_values.etcd.image.repository.clone(),
                },
            },
            operator: CiliumOperatorValues {
                image: CiliumImageValues {
                    repository: self.chart_values.operator.image.repository.clone(),
                },
            },
            nodeinit: CiliumNodeInitValues {
                image: CiliumImageValues {
                    repository: self.chart_values.nodeinit.image.repository.clone(),
                },
            },
            preflight: CiliumPreflightValues {
                image: CiliumImageValues {
                    repository: self.chart_values.preflight.image.repository.clone(),
                },
            },
            clustermesh: CiliumClustermeshValues {
                apiserver: CiliumClustermeshApiserverValues {
                    image: CiliumImageValues {
                        repository: self
                            .chart_values
                            .clustermesh
                            .apiserver
                            .image
                            .repository
                            .clone(),
                    },
                },
            },
        };

        todo!()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_cilium_values() {
        let values = CiliumValues::new();
        assert!(values.is_ok());
    }

    #[test]
    fn test_resolve_image_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels {
                container_infra_prefix: None,
            },
        };

        let addon = Addon::new(cluster).unwrap();
        let values = CiliumValues::new().unwrap();

        let image = DockerImage::parse(values.image.repository.as_str()).unwrap();

        assert_eq!(
            addon.resolve_image(&image),
            "quay.io/cilium/cilium"
        );
    }

    #[test]
    fn test_resolve_image_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels {
                container_infra_prefix: Some("registry.vexxhost.net".into()),
            },
        };

        let addon = Addon::new(cluster).unwrap();
        let values = CiliumValues::new().unwrap();

        let image = DockerImage::parse(values.image.repository.as_str()).unwrap();

        assert_eq!(
            addon.resolve_image(&image),
            "registry.vexxhost.net/cilium-cilium"
        );
    }
}
