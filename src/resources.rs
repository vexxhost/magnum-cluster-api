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

#[cfg(test)]
pub mod fixtures {
    use super::Values;
    use crate::features::{
        api_server_load_balancer, audit_log, boot_volume, openid_connect, operating_system,
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
            .cloud_ca_certificate(
                BASE64_STANDARD.encode(indoc!(
                    r#"
                    -----BEGIN CERTIFICATE-----
                    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzZz5z5z5z5z5z5z5z5z
                    -----END CERTIFICATE-----
                    "#
                )),
            )
            .cloud_controller_manager_config(
                BASE64_STANDARD.encode(indoc!(
                    r#"
                    [Global]
                    auth-url=https://auth.vexxhost.net
                    region=sjc1
                    application-credential-id=foo
                    application-credential-secret=bar
                    tls-insecure=true
                    ca-file=/etc/config/ca.crt
                    [LoadBalancer]
                    lb-provider=amphora
                    lb-method=ROUND_ROBIN
                    create-monitor=true
                    "#,
                ),
            ))
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
    use super::{fixtures::default_values, *};
    use pretty_assertions::assert_eq;

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
}
