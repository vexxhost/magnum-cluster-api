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
        OpenStackClusterTemplateTemplateSpecManagedSecurityGroupsAllNodesSecurityGroupRules,
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

pub mod admission_plugins;
pub mod api_server_floating_ip;
pub mod api_server_load_balancer;
pub mod audit_log;
pub mod boot_volume;
pub mod cloud_provider;
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

/// Recursively fixes JSON schemas to be compatible with Kubernetes ClusterClass.
///
/// When schemars generates schemas for `Option<T>`, it creates `type: ["T", "null"]`.
/// This function:
/// - Converts type arrays to just the non-null type (e.g., `["string", "null"]` → `"string"`)
/// - For object schemas, ensures optional fields (those with nullable types) are not in `required`
fn fix_type_arrays(value: &mut serde_json::Value) {
    match value {
        serde_json::Value::Object(map) => {
            // For object types, ensure optional fields (with nullable types) are not in required array
            // This must be done BEFORE we convert the type arrays
            // We need to collect the field names to remove first to avoid borrow conflicts
            let fields_to_remove = if let Some(serde_json::Value::Object(properties)) = map.get("properties") {
                if let Some(serde_json::Value::Array(required)) = map.get("required") {
                    // Collect field names that have nullable types (type is an array containing "null")
                    required
                        .iter()
                        .enumerate()
                        .filter_map(|(i, req_field)| {
                            if let serde_json::Value::String(field_name) = req_field {
                                if let Some(serde_json::Value::Object(prop_schema)) = properties.get(field_name) {
                                    // Check if this property has a nullable type (was Option<T>)
                                    if let Some(serde_json::Value::Array(arr)) = prop_schema.get("type") {
                                        // If the array contains "null", it's an optional field
                                        if arr.iter().any(|v| {
                                            if let serde_json::Value::String(s) = v {
                                                s == "null"
                                            } else {
                                                false
                                            }
                                        }) {
                                            return Some(i);
                                        }
                                    }
                                }
                            }
                            None
                        })
                        .collect::<Vec<usize>>()
                } else {
                    Vec::new()
                }
            } else {
                Vec::new()
            };

            // Now remove the fields from required array (we have mutable access now)
            if !fields_to_remove.is_empty() {
                if let Some(serde_json::Value::Array(required)) = map.get_mut("required") {
                    // Remove in reverse order to maintain indices
                    for &i in fields_to_remove.iter().rev() {
                        required.remove(i);
                    }
                }
            }

            // Fix type arrays - convert ["T", "null"] to "T"
            if let Some(type_value) = map.get_mut("type") {
                if let serde_json::Value::Array(arr) = type_value {
                    // Find the first non-null type (works for any type: string, boolean, integer, number, etc.)
                    if let Some(non_null_type) = arr.iter().find(|v| {
                        if let serde_json::Value::String(s) = v {
                            s != "null"
                        } else {
                            false
                        }
                    }) {
                        *type_value = non_null_type.clone();
                    } else if !arr.is_empty() {
                        // If all are null or no string found, use the first element
                        *type_value = arr[0].clone();
                    }
                }
            }

            // Recursively process nested objects and arrays
            for v in map.values_mut() {
                fix_type_arrays(v);
            }
        }
        serde_json::Value::Array(arr) => {
            for v in arr.iter_mut() {
                fix_type_arrays(v);
            }
        }
        _ => {}
    }
}

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
        let mut json_schema = serde_json::to_value(&root_schema).unwrap();

        // Recursively fix type arrays (e.g., ["string", "null"]) to just the non-null type (e.g., "string")
        fix_type_arrays(&mut json_schema);

        // Extract the schema field from RootSchema if it exists, otherwise use the whole object
        let schema_value = if let serde_json::Value::Object(map) = &json_schema {
            if let Some(schema) = map.get("schema") {
                schema.clone()
            } else {
                json_schema
            }
        } else {
            json_schema
        };

        let json_schema_str = serde_json::to_string(&schema_value).unwrap();

        ClusterClassVariablesSchema {
            open_apiv3_schema: serde_json::from_str(&json_schema_str).unwrap(),
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
pub static OPENSTACK_CLUSTER_TEMPLATE: LazyLock<OpenStackClusterTemplate> = LazyLock::new(|| {
    OpenStackClusterTemplate {
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
                            all_nodes_security_group_rules: Some(vec![
                                OpenStackClusterTemplateTemplateSpecManagedSecurityGroupsAllNodesSecurityGroupRules {
                                    remote_ip_prefix: Some("0.0.0.0/0".to_string()),
                                    direction: "ingress".to_string(),
                                    ether_type: Some("IPv4".to_string()),
                                    name: "Node Port (UDP, anywhere)".to_string(),
                                    port_range_min: Some(30000_i64),
                                    port_range_max: Some(32767_i64),
                                    protocol: Some("udp".to_string()),
                                    ..Default::default()
                                },
                                OpenStackClusterTemplateTemplateSpecManagedSecurityGroupsAllNodesSecurityGroupRules {
                                    remote_ip_prefix: Some("0.0.0.0/0".to_string()),
                                    direction: "ingress".to_string(),
                                    ether_type: Some("IPv4".to_string()),
                                    name: "Node Port (TCP, anywhere)".to_string(),
                                    port_range_min: Some(30000_i64),
                                    port_range_max: Some(32767_i64),
                                    protocol: Some("tcp".to_string()),
                                    ..Default::default()
                                }
                            ])
                        },
                    ),
                    ..Default::default()
                },
            },
        },
    }
});
