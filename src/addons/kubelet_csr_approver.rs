use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum::{self, ClusterError},
};
use docker_image::DockerImage;
use include_dir::include_dir;
use maplit::btreemap;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use typed_builder::TypedBuilder;

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct KubeletCsrApproverValues {
    #[serde(rename = "bypassDnsResolution")]
    bypass_dns_resolution: bool,

    #[serde(rename = "providerIpPrefixes")]
    provider_ip_prefixes: Vec<String>,

    image: KubeletCsrApproverImageValues,
}

#[derive(Debug, Deserialize, PartialEq, Serialize, TypedBuilder)]
pub struct KubeletCsrApproverImageValues {
    repository: String,
    #[serde(rename = "pullPolicy")]
    pull_policy: String,
    tag: String,
}

impl ClusterAddonValues for KubeletCsrApproverValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/kubelet-csr-approver/values.yaml"
        ));
        let values: Self = serde_yaml::from_str(file)?;

        Ok(values)
    }

    fn get_mirrored_image_name(image: DockerImage, registry: &Option<String>) -> String {
        match registry {
            Some(ref registry) => {
                format!(
                    "{}/{}",
                    registry.trim_end_matches('/'),
                    image.name.split('/').next_back().unwrap()
                )
            }
            None => image.to_string(),
        }
    }
}

impl TryFrom<magnum::Cluster> for KubeletCsrApproverValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let values = Self::defaults()?;

        let image = DockerImage::parse(&values.image.repository)?;
        Ok(Self::builder()
            .bypass_dns_resolution(true)
            .provider_ip_prefixes(vec![cluster.labels.fixed_subnet_cidr.clone()])
            .image(
                KubeletCsrApproverImageValues::builder()
                    .repository(Self::get_mirrored_image_name(
                        image,
                        &cluster.labels.container_infra_prefix,
                    ))
                    .pull_policy(values.image.pull_policy)
                    .tag(values.image.tag)
                    .build(),
            )
            .build())
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
        self.cluster.labels.is_kubelet_serving_tls_enabled()
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!(
            "{}-kubelet-csr-approver",
            self.cluster.stack_id()?
        ))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        let values = &KubeletCsrApproverValues::try_from(self.cluster.clone())
            .expect("failed to create values");

        Ok(btreemap! {
            "kubelet-csr-approver.yaml".to_owned() => helm::template_using_include_dir_with_options(
                include_dir!("magnum_cluster_api/charts/kubelet-csr-approver"),
                "kubelet-csr-approver",
                "kube-system",
                values,
                helm::TemplateOptions {
                    skip_tests: true,
                },
            )?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_values_for_cluster_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .kubelet_serving_tls_enabled("true".to_string())
                .fixed_subnet_cidr("192.168.1.0/24".to_string())
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: KubeletCsrApproverValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.bypass_dns_resolution, true);
        assert_eq!(values.provider_ip_prefixes, vec!["192.168.1.0/24".to_string()]);
        assert_eq!(
            values.image.repository,
            "ghcr.io/postfinance/kubelet-csr-approver"
        );
    }

    #[test]
    fn test_values_for_cluster_with_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .kubelet_serving_tls_enabled("true".to_string())
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let values: KubeletCsrApproverValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.image.repository, "registry.example.com/kubelet-csr-approver");
    }

    #[test]
    fn test_addon_disabled_by_default() {
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
        assert!(!addon.enabled());
    }

    #[test]
    fn test_get_manifests() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .kubelet_serving_tls_enabled("true".to_string())
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster);
        let manifests = addon.manifests().expect("failed to get manifests");
        let yaml = manifests
            .get("kubelet-csr-approver.yaml")
            .expect("manifest should exist");

        assert!(!yaml.contains("test-connection"));
        assert!(!yaml.contains("busybox"));
    }
}
