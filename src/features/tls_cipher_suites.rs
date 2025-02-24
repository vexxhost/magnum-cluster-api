use super::ClusterFeature;
use crate::{
    cluster_api::{
        kubeadmconfigtemplates::KubeadmConfigTemplate,
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
        openstackclustertemplates::OpenStackClusterTemplate,
    },
    features::ClusterClassVariablesSchemaExt,
};
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources,
    ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
    ClusterClassVariables, ClusterClassVariablesSchema,
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[schemars(with = "string")]
pub struct ApiServerTLSCipherSuitesConfig(pub String);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[schemars(with = "string")]
pub struct KubeletTLSCipherSuitesConfig(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            ClusterClassVariables {
                name: "apiServerTLSCipherSuites".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<ApiServerTLSCipherSuitesConfig>(
                ),
            },
            ClusterClassVariables {
                name: "kubeletTLSCipherSuites".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<KubeletTLSCipherSuitesConfig>(),
            },
        ]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "kubeletTLSCipherSuites".into(),
            definitions: Some(vec![
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: KubeadmControlPlaneTemplate::api_resource().api_version,
                        kind: KubeadmControlPlaneTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            control_plane: Some(true),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/tls-cipher-suites".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("apiServerTLSCipherSuites".into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/initConfiguration/nodeRegistration/kubeletExtraArgs/tls-cipher-suites".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("kubeletTLSCipherSuites".into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/nodeRegistration/kubeletExtraArgs/tls-cipher-suites".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("kubeletTLSCipherSuites".into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        }
                    ],
                },
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: KubeadmConfigTemplate::api_resource().api_version,
                        kind: KubeadmConfigTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                names: Some(vec!["default-worker".to_string()])
                            }),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/joinConfiguration/nodeRegistration/kubeletExtraArgs/tls-cipher-suites".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("kubeletTLSCipherSuites".into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                    ],
                }
            ]),
            ..Default::default()
        }]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;
    use maplit::btreemap;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "apiServerTLSCipherSuites")]
        api_server_tls_cipher_suites: ApiServerTLSCipherSuitesConfig,

        #[serde(rename = "kubeletTLSCipherSuites")]
        kubelet_tls_cipher_suites: KubeletTLSCipherSuitesConfig,
    }

    #[test]
    fn test_patches() {
        let feature = Feature {};
        let values = Values {
            api_server_tls_cipher_suites: ApiServerTLSCipherSuitesConfig("TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305".into()),
            kubelet_tls_cipher_suites: KubeletTLSCipherSuitesConfig("TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305".into()),
        };

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kubeadm_config_spec = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec;

        assert_eq!(
            kubeadm_config_spec
                .cluster_configuration
                .expect("cluster configuration should be set")
                .api_server
                .expect("api server should be set")
                .extra_args
                .expect("extra args should be set"),
            btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "profiling".to_string() => "false".to_string(),
                "tls-cipher-suites".to_string() => values.api_server_tls_cipher_suites.0.clone()
            }
        );
        assert_eq!(
            kubeadm_config_spec
                .init_configuration
                .expect("init configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "tls-cipher-suites".to_string() => values.kubelet_tls_cipher_suites.0.clone()
            }
        );
        assert_eq!(
            kubeadm_config_spec
                .join_configuration
                .expect("join configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "tls-cipher-suites".to_string() => values.kubelet_tls_cipher_suites.0.clone()
            }
        );

        assert_eq!(
            resources
                .kubeadm_config_template
                .spec
                .template
                .spec
                .expect("spec should be set")
                .join_configuration
                .expect("join configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "tls-cipher-suites".to_string() => values.kubelet_tls_cipher_suites.0.clone()
            }
        )
    }
}
