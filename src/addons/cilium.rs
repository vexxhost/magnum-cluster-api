use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum,
};
use docker_image::DockerImage;
use include_dir::include_dir;
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CiliumValues {
    image: CiliumImageValues,
    cni: CiliumCNIValues,
    certgen: CiliumCertGenValues,
    hubble: CiliumHubbleValues,
    ipam: CiliumIPAMValues,
    #[serde(rename = "k8s")]
    kubernetes: CiliumKubernetesValues,
    envoy: CiliumEnvoyValues,
    #[serde(rename = "sessionAffinity")]
    session_affinity: Option<bool>,
    etcd: CiliumEtcdValues,
    operator: CiliumOperatorValues,
    nodeinit: CiliumNodeInitValues,
    preflight: CiliumPreflightValues,
    clustermesh: CiliumClustermeshValues,
}

impl ClusterAddonValues for CiliumValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/cilium/values.yaml"
        ));
        let values: CiliumValues = serde_yaml::from_str(file)?;

        Ok(values)
    }

    // fn get_images() -> Result<Vec<DockerImage>, ClusterAddonValuesError> {
    //     let values = Self::defaults()?;

    //     Ok(vec![
    //         values.image.into(),
    //         values.certgen.image.into(),
    //         values.hubble.relay.image.into(),
    //         values.hubble.ui.backend.image.into(),
    //         values.hubble.ui.frontend.image.into(),
    //         values.envoy.image.into(),
    //         values.etcd.image.into(),
    //         values.operator.image.into(),
    //         values.nodeinit.image.into(),
    //         values.preflight.image.into(),
    //         values.clustermesh.apiserver.image.into(),
    //     ])
    // }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => {
                format!(
                    "{}/{}",
                    registry.trim_end_matches('/'),
                    image.name.replace("cilium/", "cilium-")
                )
            }
            None => image.to_string(),
        }
    }
}

impl TryFrom<magnum::Cluster> for CiliumValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let values = Self::defaults()?;

        Ok(Self {
            image: values.image.using_cluster(&cluster)?,
            cni: CiliumCNIValues {
                chaining_mode: CiliumCNIChainingMode::PortMap,
            },
            certgen: CiliumCertGenValues {
                image: values.certgen.image.using_cluster(&cluster)?,
            },
            hubble: CiliumHubbleValues {
                relay: CiliumHubbleRelayValues {
                    image: values.hubble.relay.image.using_cluster(&cluster)?,
                },
                ui: CiliumHubbleUiValues {
                    backend: CiliumHubbleUiBackendValues {
                        image: values.hubble.ui.backend.image.using_cluster(&cluster)?,
                    },
                    frontend: CiliumHubbleUiFrontendValues {
                        image: values.hubble.ui.frontend.image.using_cluster(&cluster)?,
                    },
                },
            },
            ipam: CiliumIPAMValues {
                operator: CiliumIPAMOperatorValues {
                    cluster_pool_ipv4_pod_cidr_list: vec![cluster.labels.cilium_ipv4pool.clone()],
                },
            },
            // NOTE(okozachenko): cilium has a limitation https://github.com/cilium/cilium/issues/9207
            //                    Because of that, it fails on the test
            //                    `Services should serve endpoints on same port and different protocols`.
            //                    https://github.com/kubernetes/kubernetes/pull/120069#issuecomment-2111252221
            kubernetes: CiliumKubernetesValues {
                service_proxy_name: Some("cilium".into()),
            },
            envoy: CiliumEnvoyValues {
                image: values.envoy.image.using_cluster(&cluster)?,
            },
            // NOTE(okozachenko): For users who run with kube-proxy (i.e. with Cilium's kube-proxy
            //                    replacement disabled), the ClusterIP service loadbalancing when a
            //                    request is sent from a pod running in a non-host network namespace
            //                    is still performed at the pod network interface (until
            //                    https://github.com/cilium/cilium/issues/16197 is fixed). For this
            //                    case the session affinity support is disabled by default.
            session_affinity: Some(true),
            etcd: CiliumEtcdValues {
                image: values.etcd.image.using_cluster(&cluster)?,
            },
            operator: CiliumOperatorValues {
                image: values.operator.image.using_cluster(&cluster)?,
            },
            nodeinit: CiliumNodeInitValues {
                image: values.nodeinit.image.using_cluster(&cluster)?,
            },
            preflight: CiliumPreflightValues {
                image: values.preflight.image.using_cluster(&cluster)?,
            },
            clustermesh: CiliumClustermeshValues {
                apiserver: CiliumClustermeshApiserverValues {
                    image: values.clustermesh.apiserver.image.using_cluster(&cluster)?,
                },
            },
        })
    }
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumImageValues {
    repository: String,
    tag: String,
    #[serde(rename = "useDigest")]
    use_digest: bool,
}

impl CiliumImageValues {
    pub fn using_cluster(
        &self,
        cluster: &magnum::Cluster,
    ) -> Result<Self, ClusterAddonValuesError> {
        let image = DockerImage::parse(self.repository.as_str())?;
        let repository =
            CiliumValues::get_mirrored_image_name(image, &cluster.labels.container_infra_prefix);
        let tag = cluster.labels.cilium_tag.clone();

        Ok(Self {
            repository,
            tag,
            use_digest: cluster.labels.container_infra_prefix.is_none(),
        })
    }
}

impl From<CiliumImageValues> for DockerImage {
    fn from(values: CiliumImageValues) -> Self {
        DockerImage::parse(values.repository.as_str()).expect("failed to parse image")
    }
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumImageValuesWithoutDigest {
    repository: String,
    tag: String,
}

impl CiliumImageValuesWithoutDigest {
    pub fn using_cluster(
        &self,
        cluster: &magnum::Cluster,
    ) -> Result<Self, ClusterAddonValuesError> {
        let image = DockerImage::parse(self.repository.as_str())?;
        let repository =
            CiliumValues::get_mirrored_image_name(image, &cluster.labels.container_infra_prefix);
        let tag = cluster.labels.cilium_tag.clone();

        Ok(Self { repository, tag })
    }
}

impl From<CiliumImageValuesWithoutDigest> for DockerImage {
    fn from(values: CiliumImageValuesWithoutDigest) -> Self {
        DockerImage::parse(values.repository.as_str()).expect("failed to parse image")
    }
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumCNIValues {
    #[serde(rename = "chainingMode")]
    chaining_mode: CiliumCNIChainingMode,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
enum CiliumCNIChainingMode {
    #[serde(rename = "~")]
    Default,

    #[serde(rename = "none")]
    None,

    #[serde(rename = "aws-cni")]
    AwsCni,

    #[serde(rename = "flannel")]
    Flannel,

    #[serde(rename = "generic-veth")]
    GenericVeth,

    #[serde(rename = "portmap")]
    PortMap,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumCertGenValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumHubbleValues {
    relay: CiliumHubbleRelayValues,
    ui: CiliumHubbleUiValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumIPAMValues {
    operator: CiliumIPAMOperatorValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumIPAMOperatorValues {
    #[serde(rename = "clusterPoolIPv4PodCIDRList")]
    cluster_pool_ipv4_pod_cidr_list: Vec<String>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumKubernetesValues {
    #[serde(rename = "serviceProxyName")]
    service_proxy_name: Option<String>,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumHubbleRelayValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumHubbleUiValues {
    backend: CiliumHubbleUiBackendValues,
    frontend: CiliumHubbleUiFrontendValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumHubbleUiBackendValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumHubbleUiFrontendValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumEnvoyValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumEtcdValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumOperatorValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumNodeInitValues {
    image: CiliumImageValuesWithoutDigest,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumPreflightValues {
    image: CiliumImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumClustermeshValues {
    apiserver: CiliumClustermeshApiserverValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct CiliumClustermeshApiserverValues {
    image: CiliumImageValues,
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
        self.cluster.cluster_template.network_driver == "cilium"
    }

    fn manifests<T: ClusterAddonValues + Serialize>(
        &self,
        values: &T,
    ) -> Result<String, helm::HelmTemplateError> {
        helm::template_using_include_dir(
            include_dir!("magnum_cluster_api/charts/cilium"),
            "cilium",
            "kube-system",
            values,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    // #[test]
    // fn test_cilium_values_get_images() {
    //     let images = CiliumValues::get_images().expect("failed to get images");

    //     assert_eq!(
    //         images,
    //         vec![
    //             DockerImage::parse("quay.io/cilium/cilium").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/certgen").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/hubble-relay").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/hubble-ui-backend")
    //                 .expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/hubble-ui").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/cilium-envoy").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/cilium-etcd-operator")
    //                 .expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/operator").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/startup-script").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/cilium").expect("failed to parse image"),
    //             DockerImage::parse("quay.io/cilium/clustermesh-apiserver")
    //                 .expect("failed to parse image"),
    //         ]
    //     );
    // }

    #[test]
    fn test_cilium_values_for_cluster_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CiliumValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.image,
            CiliumImageValues {
                repository: "quay.io/cilium/cilium".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.certgen.image,
            CiliumImageValues {
                repository: "quay.io/cilium/certgen".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.hubble.relay.image,
            CiliumImageValues {
                repository: "quay.io/cilium/hubble-relay".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.hubble.ui.backend.image,
            CiliumImageValues {
                repository: "quay.io/cilium/hubble-ui-backend".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.hubble.ui.frontend.image,
            CiliumImageValues {
                repository: "quay.io/cilium/hubble-ui".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.envoy.image,
            CiliumImageValues {
                repository: "quay.io/cilium/cilium-envoy".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.etcd.image,
            CiliumImageValues {
                repository: "quay.io/cilium/cilium-etcd-operator".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.operator.image,
            CiliumImageValues {
                repository: "quay.io/cilium/operator".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.nodeinit.image,
            CiliumImageValuesWithoutDigest {
                repository: "quay.io/cilium/startup-script".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
            }
        );
        assert_eq!(
            values.preflight.image,
            CiliumImageValues {
                repository: "quay.io/cilium/cilium".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
        assert_eq!(
            values.clustermesh.apiserver.image,
            CiliumImageValues {
                repository: "quay.io/cilium/clustermesh-apiserver".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: true,
            }
        );
    }

    #[test]
    fn test_cilium_values_for_cluster_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CiliumValues = cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-cilium".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.certgen.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-certgen".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.hubble.relay.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-hubble-relay".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.hubble.ui.backend.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-hubble-ui-backend".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.hubble.ui.frontend.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-hubble-ui".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.envoy.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-cilium-envoy".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.etcd.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-cilium-etcd-operator".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.operator.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-operator".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.nodeinit.image,
            CiliumImageValuesWithoutDigest {
                repository: "registry.example.com/cilium-startup-script".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
            }
        );
        assert_eq!(
            values.preflight.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-cilium".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
        );
        assert_eq!(
            values.clustermesh.apiserver.image,
            CiliumImageValues {
                repository: "registry.example.com/cilium-clustermesh-apiserver".to_string(),
                tag: cluster.labels.cilium_tag.clone(),
                use_digest: false,
            }
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
        };

        let addon = Addon::new(cluster.clone());
        let values: CiliumValues = cluster.clone().try_into().expect("failed to create values");
        addon.manifests(&values).expect("failed to get manifests");
    }
}
