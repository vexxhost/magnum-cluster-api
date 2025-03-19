use crate::{
    addons::{ClusterAddon, ClusterAddonValues, ClusterAddonValuesError},
    magnum,
};
use docker_image::DockerImage;
use include_dir::include_dir;
use k8s_openapi::api::core::v1::{HostPathVolumeSource, Volume, VolumeMount};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CloudControllerManagerValues {
    image: CloudControllerManagerImageValues,

    secret: CloudControllerManagerSecretValues,

    #[serde(rename = "extraVolumes")]
    extra_volumes: Vec<Volume>,

    #[serde(rename = "extraVolumeMounts")]
    extra_volume_mounts: Vec<VolumeMount>,

    cluster: CloudControllerManagerClusterValues,
}

impl ClusterAddonValues for CloudControllerManagerValues {
    fn defaults() -> Result<Self, ClusterAddonValuesError> {
        let file = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/magnum_cluster_api/charts/openstack-cloud-controller-manager/values.yaml"
        ));
        let values: CloudControllerManagerValues = serde_yaml::from_str(file)?;

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
                    image.name.split('/').last().unwrap()
                )
            }
            None => image.to_string(),
        }
    }
}

impl TryFrom<magnum::Cluster> for CloudControllerManagerValues {
    type Error = ClusterAddonValuesError;

    fn try_from(cluster: magnum::Cluster) -> Result<Self, ClusterAddonValuesError> {
        let values = Self::defaults()?;

        let image = DockerImage::parse(&values.image.repository)?;

        Ok(Self {
            image: CloudControllerManagerImageValues {
                repository: Self::get_mirrored_image_name(
                    image,
                    &cluster.labels.container_infra_prefix,
                ),
                tag: cluster.labels.cloud_provider_tag,
            },
            secret: CloudControllerManagerSecretValues { create: false },
            extra_volumes: vec![
                Volume {
                    name: "k8s-certs".to_string(),
                    host_path: Some(HostPathVolumeSource {
                        path: "/etc/kubernetes/pki".to_string(),
                        type_: Some("Directory".to_string()),
                    }),
                    ..Default::default()
                },
                Volume {
                    name: "ca-certs".to_string(),
                    host_path: Some(HostPathVolumeSource {
                        path: "/etc/ssl/certs".to_string(),
                        type_: Some("DirectoryOrCreate".to_string()),
                    }),
                    ..Default::default()
                },
            ],
            extra_volume_mounts: vec![
                VolumeMount {
                    name: "k8s-certs".to_string(),
                    mount_path: "/etc/kubernetes/pki".to_string(),
                    read_only: Some(true),
                    ..Default::default()
                },
                VolumeMount {
                    name: "ca-certs".to_string(),
                    mount_path: "/etc/ssl/certs".to_string(),
                    read_only: Some(true),
                    ..Default::default()
                },
            ],
            cluster: CloudControllerManagerClusterValues { name: cluster.uuid },
        })
    }
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CloudControllerManagerImageValues {
    repository: String,
    tag: String,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CloudControllerManagerSecretValues {
    create: bool,
}

#[derive(Debug, Deserialize, PartialEq, Serialize)]
pub struct CloudControllerManagerClusterValues {
    name: String,
}

pub struct Addon {}

impl Addon {}

impl ClusterAddon for Addon {
    fn new(_cluster: magnum::Cluster) -> Self {
        Self {}
    }

    fn enabled(&self) -> bool {
        true
    }

    fn manifests<T: ClusterAddonValues + Serialize>(
        &self,
        values: &T,
    ) -> Result<String, helm::HelmTemplateError> {
        helm::template_using_include_dir(
            include_dir!("magnum_cluster_api/charts/openstack-cloud-controller-manager"),
            "openstack-ccm",
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
    fn test_occm_values_for_cluster_without_custom_registry() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CloudControllerManagerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.image.repository,
            "registry.k8s.io/provider-os/openstack-cloud-controller-manager"
        );
        assert_eq!(values.image.tag, "v1.30.0");
    }

    #[test]
    fn test_occm_values_for_cluster_with_custom_registry_and_tag() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("registry.example.com".to_string()))
                .cloud_provider_tag("v1.32.0".to_string())
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CloudControllerManagerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(
            values.image.repository,
            "registry.example.com/openstack-cloud-controller-manager"
        );
        assert_eq!(values.image.tag, "v1.32.0");
    }

    #[test]
    fn test_occm_values_for_cluster() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
        };

        let values: CloudControllerManagerValues =
            cluster.clone().try_into().expect("failed to create values");

        assert_eq!(values.secret.create, false);
        assert_eq!(
            values.extra_volumes,
            vec![
                Volume {
                    name: "k8s-certs".to_string(),
                    host_path: Some(HostPathVolumeSource {
                        path: "/etc/kubernetes/pki".to_string(),
                        type_: Some("Directory".to_string()),
                    }),
                    ..Default::default()
                },
                Volume {
                    name: "ca-certs".to_string(),
                    host_path: Some(HostPathVolumeSource {
                        path: "/etc/ssl/certs".to_string(),
                        type_: Some("DirectoryOrCreate".to_string()),
                    }),
                    ..Default::default()
                },
            ]
        );
        assert_eq!(
            values.extra_volume_mounts,
            vec![
                VolumeMount {
                    name: "k8s-certs".to_string(),
                    mount_path: "/etc/kubernetes/pki".to_string(),
                    read_only: Some(true),
                    ..Default::default()
                },
                VolumeMount {
                    name: "ca-certs".to_string(),
                    mount_path: "/etc/ssl/certs".to_string(),
                    read_only: Some(true),
                    ..Default::default()
                },
            ]
        );
        assert_eq!(values.cluster.name, cluster.uuid,);
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
        let values: CloudControllerManagerValues =
            cluster.clone().try_into().expect("failed to create values");
        addon.manifests(&values).expect("failed to get manifests");
    }
}
