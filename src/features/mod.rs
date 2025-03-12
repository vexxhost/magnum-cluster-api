#[cfg(test)]
mod test;

use crate::cluster_api::{
    clusterclasses::{ClusterClassPatches, ClusterClassVariables, ClusterClassVariablesSchema},
    kubeadmconfigtemplates::{
        KubeadmConfigTemplate, KubeadmConfigTemplateSpec, KubeadmConfigTemplateTemplate,
        KubeadmConfigTemplateTemplateSpec, KubeadmConfigTemplateTemplateSpecDiskSetup,
        KubeadmConfigTemplateTemplateSpecFiles, KubeadmConfigTemplateTemplateSpecFilesEncoding,
        KubeadmConfigTemplateTemplateSpecJoinConfiguration,
        KubeadmConfigTemplateTemplateSpecJoinConfigurationNodeRegistration,
    },
    kubeadmcontrolplanetemplates::{
        KubeadmControlPlaneTemplate, KubeadmControlPlaneTemplateSpec,
        KubeadmControlPlaneTemplateTemplate, KubeadmControlPlaneTemplateTemplateSpec,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationControllerManager,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationEtcd,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationEtcdLocal,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationScheduler,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetup,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFormat,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecInitConfiguration,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecInitConfigurationNodeRegistration,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecJoinConfiguration,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecJoinConfigurationNodeRegistration,
        KubeadmControlPlaneTemplateTemplateSpecRolloutBefore,
    },
    openstackclustertemplates::{
        OpenStackClusterTemplate, OpenStackClusterTemplateSpec, OpenStackClusterTemplateTemplate,
        OpenStackClusterTemplateTemplateSpec, OpenStackClusterTemplateTemplateSpecIdentityRef,
        OpenStackClusterTemplateTemplateSpecManagedSecurityGroups,
    },
    openstackmachinetemplates::{
        OpenStackMachineTemplate, OpenStackMachineTemplateSpec, OpenStackMachineTemplateTemplate,
        OpenStackMachineTemplateTemplateSpec, OpenStackMachineTemplateTemplateSpecIdentityRef,
        OpenStackMachineTemplateTemplateSpecImage,
    },
};
use base64::prelude::*;
use maplit::btreemap;
use schemars::{gen::SchemaGenerator, JsonSchema};
use std::sync::LazyLock;

pub mod api_server_load_balancer;
pub mod audit_log;
pub mod boot_volume;
pub mod cluster_identity;
pub mod containerd_config;
pub mod control_plane_availability_zones;
pub mod disable_api_server_floating_ip;
pub mod external_network;
pub mod flavors;
pub mod image_repository;
pub mod images;
pub mod keystone_auth;
pub mod networks;
pub mod openid_connect;
pub mod operating_system;
pub mod server_groups;
pub mod ssh_key;
pub mod tls;
pub mod volumes;

pub trait ClusterFeatureVariables: Sync {
    fn variables(&self) -> Vec<ClusterClassVariables>;
}

pub trait ClusterFeaturePatches: Sync {
    fn patches(&self) -> Vec<ClusterClassPatches>;
}

pub trait ClusterFeature: Sync + ClusterFeatureVariables + ClusterFeaturePatches {}

impl<T> ClusterFeature for T where T: Sync + ClusterFeatureVariables + ClusterFeaturePatches {}

pub struct ClusterFeatureEntry {
    pub feature: &'static dyn ClusterFeature,
}

inventory::collect!(ClusterFeatureEntry);

pub trait ClusterClassVariablesSchemaExt {
    fn from_object<T: JsonSchema>() -> Self;
    fn from_root_schema(root_schema: schemars::schema::RootSchema) -> Self;
}

impl ClusterClassVariablesSchemaExt for ClusterClassVariablesSchema {
    fn from_object<T: JsonSchema>() -> Self {
        let gen = SchemaGenerator::default();
        let schema = gen.into_root_schema_for::<T>();
        Self::from_root_schema(schema)
    }

    fn from_root_schema(root_schema: schemars::schema::RootSchema) -> Self {
        let json_schema = serde_json::to_string(&root_schema).unwrap();

        ClusterClassVariablesSchema {
            open_apiv3_schema: serde_json::from_str(&json_schema).unwrap(),
        }
    }
}

/// This is a static instance of the `KubeadmControlPlaneTemplate` that is
/// created once and then used for all objects.
pub static KUBEADM_CONTROL_PLANE_TEMPLATE: LazyLock<KubeadmControlPlaneTemplate> = LazyLock::new(
    || {
        KubeadmControlPlaneTemplate {
            metadata: Default::default(),
            spec: KubeadmControlPlaneTemplateSpec {
                template: KubeadmControlPlaneTemplateTemplate {
                    spec: KubeadmControlPlaneTemplateTemplateSpec {
                        rollout_before: Some(KubeadmControlPlaneTemplateTemplateSpecRolloutBefore {
                            certificates_expiry_days: Some(21),
                        }),
                        kubeadm_config_spec: KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec {
                            cluster_configuration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration {
                                api_server: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer {
                                    extra_args: Some({
                                        btreemap! {
                                            "cloud-provider".to_string() => "external".to_string(),
                                            "profiling".to_string() => "false".to_string(),
                                        }
                                    }),
                                    // Note(oleks): Add this as default as a workaround of the json patch limitation # noqa: E501
                                    // https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass#json-patches-tips--tricks
                                    extra_volumes: Some(vec![
                                        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                            name: "webhooks".to_string(),
                                            host_path: "/etc/kubernetes/webhooks".to_string(),
                                            mount_path: "/etc/kubernetes/webhooks".to_string(),
                                            ..Default::default()
                                        }
                                    ]),
                                    ..Default::default()
                                }),
                                etcd: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationEtcd{
                                    local: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationEtcdLocal {
                                        extra_args: Some(btreemap! {
                                            "listen-metrics-urls".to_string() => "http://0.0.0.0:2381".to_string(),
                                        }),
                                        ..Default::default()
                                    }),
                                    ..Default::default()
                                }),
                                controller_manager: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationControllerManager {
                                    extra_args: Some(btreemap! {
                                        "bind-address".to_string() => "0.0.0.0".to_string(),
                                        "cloud-provider".to_string() => "external".to_string(),
                                        "profiling".to_string() => "false".to_string(),
                                    }),
                                    ..Default::default()
                                }),
                                scheduler: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationScheduler {
                                    extra_args: Some(btreemap! {
                                        "bind-address".to_string() => "0.0.0.0".to_string(),
                                        "profiling".to_string() => "false".to_string(),
                                    }),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }),
                            disk_setup: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetup {
                                ..Default::default()
                            }),
                            files: Some(vec![
                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                    path: "/etc/kubernetes/audit-policy/apiserver-audit-policy.yaml".to_string(),
                                    permissions: Some("0600".to_string()),
                                    content: Some(
                                        BASE64_STANDARD.encode(include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/audit/policy.yaml")))
                                    ),
                                    encoding: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64),
                                    ..Default::default()
                                },
                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                    path: "/etc/kubernetes/webhooks/webhookconfig.yaml".to_string(),
                                    permissions: Some("0644".to_string()),
                                    owner: Some("root:root".to_string()),
                                    content: Some(
                                        BASE64_STANDARD.encode(include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/keystone-auth/webhook.yaml")))
                                    ),
                                    encoding: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64),
                                    ..Default::default()
                                },
                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                    path: "/run/kubeadm/configure-kube-proxy.sh".to_string(),
                                    permissions: Some("0755".to_string()),
                                    content: Some(
                                        BASE64_STANDARD.encode(include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/data/kubeadm/configure-kube-proxy.sh")))
                                    ),
                                    encoding: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64),
                                    ..Default::default()
                                }
                            ]),
                            format: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFormat::CloudConfig),
                            init_configuration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecInitConfiguration {
                                node_registration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecInitConfigurationNodeRegistration {
                                    name: Some("{{ local_hostname }}".to_string()),
                                    kubelet_extra_args: Some(btreemap! {
                                        "cloud-provider".to_string() => "external".to_string(),
                                    }),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }),
                            join_configuration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecJoinConfiguration {
                                node_registration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecJoinConfigurationNodeRegistration {
                                    name: Some("{{ local_hostname }}".to_string()),
                                    kubelet_extra_args: Some(btreemap! {
                                        "cloud-provider".to_string() => "external".to_string(),
                                    }),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }),
                            pre_kubeadm_commands: Some(vec![
                                "rm /var/lib/etcd/lost+found -rf".to_string(),
                                "bash /run/kubeadm/configure-kube-proxy.sh".to_string(),
                            ]),
                            post_kubeadm_commands: Some(vec![
                                "echo PLACEHOLDER".to_string(),
                            ]),
                            ..Default::default()
                        },
                        ..Default::default()
                    },
                    ..Default::default()
                },
            }
        }
    },
);

/// This is a static instance of the `OpenStackClusterTemplate` that is
/// created once and then used for all objects.
pub static KUBEADM_CONFIG_TEMPLATE: LazyLock<KubeadmConfigTemplate> =
    LazyLock::new(|| KubeadmConfigTemplate {
        metadata: Default::default(),
        spec: KubeadmConfigTemplateSpec {
            template: KubeadmConfigTemplateTemplate {
                spec: Some(KubeadmConfigTemplateTemplateSpec {
                    disk_setup: Some(KubeadmConfigTemplateTemplateSpecDiskSetup {
                        ..Default::default()
                    }),
                    files: Some(vec![KubeadmConfigTemplateTemplateSpecFiles {
                        path: "/etc/kubernetes/.placeholder".to_string(),
                        permissions: Some("0644".to_string()),
                        content: Some(BASE64_STANDARD.encode("PLACEHOLDER")),
                        encoding: Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64),
                        ..Default::default()
                    }]),
                    join_configuration: Some(KubeadmConfigTemplateTemplateSpecJoinConfiguration {
                        node_registration: Some(
                            KubeadmConfigTemplateTemplateSpecJoinConfigurationNodeRegistration {
                                name: Some("{{ local_hostname }}".to_string()),
                                kubelet_extra_args: Some(btreemap! {
                                    "cloud-provider".to_string() => "external".to_string(),
                                }),
                                ..Default::default()
                            },
                        ),
                        ..Default::default()
                    }),
                    ..Default::default()
                }),
                ..Default::default()
            },
        },
    });

/// This is a static instance of the `OpenStackClusterTemplate` that is
/// created once and then used for all objects.
pub static OPENSTACK_MACHINE_TEMPLATE: LazyLock<OpenStackMachineTemplate> =
    LazyLock::new(|| OpenStackMachineTemplate {
        metadata: Default::default(),
        spec: OpenStackMachineTemplateSpec {
            template: OpenStackMachineTemplateTemplate {
                spec: OpenStackMachineTemplateTemplateSpec {
                    flavor: Some("PLACEHOLDER".to_string()),
                    identity_ref: Some(OpenStackMachineTemplateTemplateSpecIdentityRef {
                        name: "PLACEHOLDER".to_string(),
                        cloud_name: "default".to_string(),
                        ..Default::default()
                    }),
                    image: OpenStackMachineTemplateTemplateSpecImage {
                        id: Some("00000000-0000-0000-0000-000000000000".to_string()),
                        ..Default::default()
                    },
                    ..Default::default()
                },
            },
        },
    });

/// This is a static instance of the `OpenStackClusterTemplate` that is
/// created once and then used for all objects.
pub static OPENSTACK_CLUSTER_TEMPLATE: LazyLock<OpenStackClusterTemplate> =
    LazyLock::new(|| OpenStackClusterTemplate {
        metadata: Default::default(),
        spec: OpenStackClusterTemplateSpec {
            template: OpenStackClusterTemplateTemplate {
                spec: OpenStackClusterTemplateTemplateSpec {
                    identity_ref: OpenStackClusterTemplateTemplateSpecIdentityRef {
                        name: "PLACEHOLDER".into(),
                        cloud_name: "default".into(),
                        ..Default::default()
                    },
                    managed_security_groups: Some(
                        OpenStackClusterTemplateTemplateSpecManagedSecurityGroups {
                            allow_all_in_cluster_traffic: true,
                            ..Default::default()
                        },
                    ),
                    ..Default::default()
                },
            },
        },
    });
