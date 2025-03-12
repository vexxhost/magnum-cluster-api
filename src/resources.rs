include!(concat!(env!("OUT_DIR"), "/values.rs"));

use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClass, ClusterClassControlPlane, ClusterClassControlPlaneMachineHealthCheck,
            ClusterClassControlPlaneMachineHealthCheckUnhealthyConditions,
            ClusterClassControlPlaneMachineInfrastructure, ClusterClassInfrastructure,
            ClusterClassPatches, ClusterClassSpec, ClusterClassVariables, ClusterClassWorkers,
            ClusterClassWorkersMachineDeployments,
            ClusterClassWorkersMachineDeploymentsMachineHealthCheck,
            ClusterClassWorkersMachineDeploymentsMachineHealthCheckUnhealthyConditions,
            ClusterClassWorkersMachineDeploymentsTemplate,
            ClusterClassWorkersMachineDeploymentsTemplateBootstrap,
            ClusterClassWorkersMachineDeploymentsTemplateInfrastructure,
        },
        clusters::ClusterTopologyVariables,
        kubeadmconfigtemplates::KubeadmConfigTemplate,
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
        openstackclustertemplates::OpenStackClusterTemplate,
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::ClusterFeatureEntry,
};
use k8s_openapi::{api::core::v1::ObjectReference, apimachinery::pkg::util::intstr::IntOrString};
use kube::{api::ObjectMeta, CustomResourceExt};

pub struct ClusterClassBuilder {
    variables: Vec<ClusterClassVariables>,
    patches: Vec<ClusterClassPatches>,
}

impl ClusterClassBuilder {
    pub fn new() -> Self {
        Self {
            variables: Vec::new(),
            patches: Vec::new(),
        }
    }

    pub fn build(self, metadata: ObjectMeta) -> ClusterClass {
        ClusterClass {
            metadata: metadata.clone(),
            spec: ClusterClassSpec {
                control_plane: Some(ClusterClassControlPlane {
                    machine_health_check: Some(ClusterClassControlPlaneMachineHealthCheck {
                        max_unhealthy: Some(IntOrString::String("80%".to_string())),
                        unhealthy_conditions: Some(vec![
                            ClusterClassControlPlaneMachineHealthCheckUnhealthyConditions {
                                r#type: "Ready".to_string(),
                                timeout: "5m0s".to_string(),
                                status: "False".to_string(),
                            },
                            ClusterClassControlPlaneMachineHealthCheckUnhealthyConditions {
                                r#type: "Ready".to_string(),
                                timeout: "5m0s".to_string(),
                                status: "Unknown".to_string(),
                            },
                        ]),
                        ..Default::default()
                    }),
                    machine_infrastructure: Some(ClusterClassControlPlaneMachineInfrastructure {
                        r#ref: ObjectReference {
                            api_version: Some(OpenStackMachineTemplate::api_resource().api_version),
                            kind: Some(OpenStackMachineTemplate::api_resource().kind),
                            name: metadata.name.clone(),
                            namespace: metadata.namespace.clone(),
                            ..Default::default()
                        },
                    }),
                    node_volume_detach_timeout: Some("5m0s".to_string()),
                    r#ref: ObjectReference {
                        api_version: Some(KubeadmControlPlaneTemplate::api_resource().api_version),
                        kind: Some(KubeadmControlPlaneTemplate::api_resource().kind),
                        name: metadata.name.clone(),
                        namespace: metadata.namespace.clone(),
                        ..Default::default()
                    },
                    ..Default::default()
                }),
                infrastructure: Some(ClusterClassInfrastructure {
                    r#ref: ObjectReference {
                        api_version: Some(OpenStackClusterTemplate::api_resource().api_version),
                        kind: Some(OpenStackClusterTemplate::api_resource().kind),
                        name: metadata.name.clone(),
                        namespace: metadata.namespace.clone(),
                        ..Default::default()
                    },
                }),
                patches: Some(self.patches),
                variables: Some(self.variables),
                workers: Some(ClusterClassWorkers {
                    machine_deployments: Some(vec![
                        ClusterClassWorkersMachineDeployments {
                            class: "default-worker".to_string(),
                            machine_health_check: Some(ClusterClassWorkersMachineDeploymentsMachineHealthCheck {
                                max_unhealthy: Some(IntOrString::String("80%".to_string())),
                                unhealthy_conditions: Some(vec![
                                    ClusterClassWorkersMachineDeploymentsMachineHealthCheckUnhealthyConditions {
                                        r#type: "Ready".to_string(),
                                        timeout: "5m0s".to_string(),
                                        status: "False".to_string(),
                                    },
                                    ClusterClassWorkersMachineDeploymentsMachineHealthCheckUnhealthyConditions {
                                        r#type: "Ready".to_string(),
                                        timeout: "5m0s".to_string(),
                                        status: "Unknown".to_string(),
                                    },
                                ]),
                                ..Default::default()
                            }),
                            node_volume_detach_timeout: Some("5m0s".to_string()),
                            template: ClusterClassWorkersMachineDeploymentsTemplate {
                                bootstrap: ClusterClassWorkersMachineDeploymentsTemplateBootstrap {
                                    r#ref: ObjectReference {
                                        api_version: Some(KubeadmConfigTemplate::api_resource().api_version),
                                        kind: Some(KubeadmConfigTemplate::api_resource().kind),
                                        name: metadata.name.clone(),
                                        namespace: metadata.namespace.clone(),
                                        ..Default::default()
                                    },
                                },
                                infrastructure: ClusterClassWorkersMachineDeploymentsTemplateInfrastructure {
                                    r#ref: ObjectReference {
                                        api_version: Some(OpenStackMachineTemplate::api_resource().api_version),
                                        kind: Some(OpenStackMachineTemplate::api_resource().kind),
                                        name: metadata.name.clone(),
                                        namespace: metadata.namespace.clone(),
                                        ..Default::default()
                                    },
                                },
                                ..Default::default()
                            },
                            ..Default::default()
                        }
                    ]),
                    ..Default::default()
                }),
            },
            ..Default::default()
        }
    }

    pub fn default(metadata: ObjectMeta) -> ClusterClass {
        let mut cc = ClusterClassBuilder::new();

        for entry in inventory::iter::<ClusterFeatureEntry> {
            cc.variables.extend(entry.feature.variables());
            cc.patches.extend(entry.feature.patches());
        }

        cc.build(metadata)
    }
}

impl From<Values> for Vec<ClusterTopologyVariables> {
    fn from(values: Values) -> Self {
        let json_values = serde_json::to_value(values).expect("Failed to serialize values");

        if let serde_json::Value::Object(map) = json_values {
            // For each (key, value) pair in the map,
            // create a ClusterTopologyVariables instance.
            map.into_iter()
                .map(|(key, value)| ClusterTopologyVariables {
                    name: key,
                    value,
                    ..Default::default()
                })
                .collect()
        } else {
            panic!("Expected Values to serialize to a JSON object");
        }
    }
}

#[cfg(test)]
pub mod fixtures {
    use crate::{
        features::{
            api_server_load_balancer, audit_log, boot_volume, openid_connect, operating_system,
        },
        resources::Values,
    };
    use base64::prelude::*;
    use indoc::indoc;

    pub fn default_values() -> Values {
        Values::builder()
            .api_server_load_balancer(
                api_server_load_balancer::APIServerLoadBalancerConfig::builder()
                    .enabled(true)
                    .provider("amphora".into())
                    .build(),
            )
            .audit_log(
                audit_log::AuditLogConfig::builder()
                    .enabled(false)
                    .max_age("30".to_string())
                    .max_backup("10".to_string())
                    .max_size("100".to_string())
                    .build(),
            )
            .boot_volume(boot_volume::BootVolumeConfig::builder().r#type("nvme".into()).size(0).build())
            .cluster_identity_ref_name("identity-ref-name".into())
            .containerd_config(
                BASE64_STANDARD.encode(indoc! {r#"
                    # Use config version 2 to enable new configuration fields.
                    # Config file is parsed as version 1 by default.
                    version = 2

                    imports = ["/etc/containerd/conf.d/*.toml"]

                    [plugins]
                    [plugins."io.containerd.grpc.v1.cri"]
                        sandbox_image = "{sandbox_image}"
                    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
                        runtime_type = "io.containerd.runc.v2"
                    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
                        SystemdCgroup = true
                "#})
            )
            .systemd_proxy_config(
                BASE64_STANDARD.encode(indoc! {r#"
                    [Service]
                    Environment="http_proxy=http://proxy.internal:3128"
                    Environment="HTTP_PROXY=http://proxy.internal:3128"
                    Environment="https_proxy=https://proxy.internal:3129"
                    Environment="HTTPS_PROXY=https://proxy.internal:3129"
                    Environment="no_proxy=localhost,"
                    Environment="NO_PROXY=localhost,"
                "#})
            )
            .control_plane_availability_zones(vec!["zone1".into(), "zone2".into()])
            .disable_api_server_floating_ip(true)
            .external_network_id("external-network-id".into())
            .control_plane_flavor("control-plane".into())
            .flavor("worker".into())
            .image_repository("registry.example.com/cluster-api".into())
            .image_uuid("bar".into())
            .enable_keystone_auth(true)
            .node_cidr("10.0.0.0/24".into())
            .dns_nameservers(vec!["1.1.1.1".into()])
            .fixed_network_id("".into())
            .fixed_subnet_id("".into())
            .openid_connect(
                openid_connect::OpenIdConnectConfig::builder()
                    .issuer_url("https://example.com".to_string())
                    .client_id("client-id".to_string())
                    .username_claim("email".to_string())
                    .username_prefix("email:".to_string())
                    .groups_claim("groups".to_string())
                    .groups_prefix("groups:".to_string())
                    .build(),
            )
            .operating_system(operating_system::OperatingSystem::Ubuntu)
            .apt_proxy_config("bar".into())
            .server_group_id("server-group-1".into())
            .is_server_group_diff_failure_domain(true)
            .ssh_key_name("my-key".into())
            .api_server_tls_cipher_suites("TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305".into())
            .api_server_sans("".into())
            .kubelet_tls_cipher_suites("TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305".into())
            .hardware_disk_bus("".into())
            .enable_docker_volume(false)
            .docker_volume_size(0)
            .docker_volume_type("".into())
            .enable_etcd_volume(false)
            .etcd_volume_size(0)
            .etcd_volume_type("".into())
            .availability_zone("az1".into())
            .build()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cluster_api::clusters::ClusterTopologyVariables, resources::fixtures::default_values,
    };
    use pretty_assertions::assert_eq;
    use serde_json::json;

    #[test]
    fn test_default_cluster_class() {
        let metadata = ObjectMeta {
            name: Some("test".to_string()),
            namespace: Some("default".to_string()),
            ..Default::default()
        };
        let cluster_class = ClusterClassBuilder::default(metadata);

        assert_eq!(cluster_class.metadata.name, Some("test".into()));
        assert_eq!(cluster_class.metadata.namespace, Some("default".into()));

        assert_eq!(cluster_class.spec.control_plane.is_some(), true);
        assert_eq!(cluster_class.spec.infrastructure.is_some(), true);
        assert_eq!(cluster_class.spec.patches.is_some(), true);
        assert_eq!(cluster_class.spec.variables.is_some(), true);
        assert_eq!(cluster_class.spec.workers.is_some(), true);
    }

    #[test]
    fn test_convert_values_to_cluster_topology_variables() {
        let values = default_values();
        let variables: Vec<ClusterTopologyVariables> = values.into();

        assert_eq!(variables.len(), 35);

        for var in &variables {
            match var.name.as_str() {
                "apiServerLoadBalancer" => {
                    assert_eq!(var.value, json!(&default_values().api_server_load_balancer));
                }
                "auditLog" => {
                    assert_eq!(var.value, json!(default_values().audit_log));
                }
                "bootVolume" => {
                    assert_eq!(var.value, json!(default_values().boot_volume));
                }
                "clusterIdentityRefName" => {
                    assert_eq!(var.value, json!(default_values().cluster_identity_ref_name));
                }
                "containerdConfig" => {
                    assert_eq!(var.value, json!(default_values().containerd_config));
                }
                "systemdProxyConfig" => {
                    assert_eq!(var.value, json!(default_values().systemd_proxy_config));
                }
                "controlPlaneAvailabilityZones" => {
                    assert_eq!(
                        var.value,
                        json!(default_values().control_plane_availability_zones)
                    );
                }
                "disableAPIServerFloatingIP" => {
                    assert_eq!(
                        var.value,
                        json!(default_values().disable_api_server_floating_ip)
                    );
                }
                "externalNetworkId" => {
                    assert_eq!(var.value, json!(default_values().external_network_id));
                }
                "controlPlaneFlavor" => {
                    assert_eq!(var.value, json!(default_values().control_plane_flavor));
                }
                "flavor" => {
                    assert_eq!(var.value, json!(default_values().flavor));
                }
                "imageRepository" => {
                    assert_eq!(var.value, json!(default_values().image_repository));
                }
                "imageUUID" => {
                    assert_eq!(var.value, json!(default_values().image_uuid));
                }
                "enableKeystoneAuth" => {
                    assert_eq!(var.value, json!(default_values().enable_keystone_auth));
                }
                "nodeCidr" => {
                    assert_eq!(var.value, json!(default_values().node_cidr));
                }
                "dnsNameservers" => {
                    assert_eq!(var.value, json!(default_values().dns_nameservers));
                }
                "fixedNetworkId" => {
                    assert_eq!(var.value, json!(default_values().fixed_network_id));
                }
                "fixedSubnetId" => {
                    assert_eq!(var.value, json!(default_values().fixed_subnet_id));
                }
                "openidConnect" => {
                    assert_eq!(var.value, json!(default_values().openid_connect));
                }
                "operatingSystem" => {
                    assert_eq!(var.value, json!(default_values().operating_system));
                }
                "aptProxyConfig" => {
                    assert_eq!(var.value, json!(default_values().apt_proxy_config));
                }
                "serverGroupId" => {
                    assert_eq!(var.value, json!(default_values().server_group_id));
                }
                "isServerGroupDiffFailureDomain" => {
                    assert_eq!(
                        var.value,
                        json!(default_values().is_server_group_diff_failure_domain)
                    );
                }
                "sshKeyName" => {
                    assert_eq!(var.value, json!(default_values().ssh_key_name));
                }
                "apiServerTLSCipherSuites" => {
                    assert_eq!(
                        var.value,
                        json!(default_values().api_server_tls_cipher_suites)
                    );
                }
                "kubeletTLSCipherSuites" => {
                    assert_eq!(var.value, json!(default_values().kubelet_tls_cipher_suites));
                }
                "apiServerSANs" => {
                    assert_eq!(var.value, json!(default_values().api_server_sans));
                },
                "hardwareDiskBus" => {
                    assert_eq!(var.value, json!(default_values().hardware_disk_bus));
                },
                "enableDockerVolume" => {
                    assert_eq!(var.value, json!(default_values().enable_docker_volume));
                }
                "dockerVolumeSize" => {
                    assert_eq!(var.value, json!(default_values().docker_volume_size));
                }
                "dockerVolumeType" => {
                    assert_eq!(var.value, json!(default_values().docker_volume_type));
                }
                "enableEtcdVolume" => {
                    assert_eq!(var.value, json!(default_values().enable_etcd_volume));
                }
                "etcdVolumeSize" => {
                    assert_eq!(var.value, json!(default_values().etcd_volume_size));
                }
                "etcdVolumeType" => {
                    assert_eq!(var.value, json!(default_values().etcd_volume_type));
                }
                "availabilityZone" => {
                    assert_eq!(var.value, json!(default_values().availability_zone));
                }
                other => panic!("Unexpected field name: {}", other),
            }
        }
    }
}
