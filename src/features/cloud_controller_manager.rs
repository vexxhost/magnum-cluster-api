use super::ClusterFeature;
use crate::{
    cluster_api::{
        kubeadmconfigtemplates::{
            KubeadmConfigTemplate, KubeadmConfigTemplateTemplateSpecFiles,
            KubeadmConfigTemplateTemplateSpecFilesEncoding,
        },
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding,
        },
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
pub struct CloudCACertificatesConfig(pub String);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[schemars(with = "string")]
pub struct CloudControllerManagerConfig(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            ClusterClassVariables {
                name: "cloudCaCert".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<CloudCACertificatesConfig>(),
            },
            ClusterClassVariables {
                name: "cloudControllerManagerConfig".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<CloudControllerManagerConfig>(),
            },
        ]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "cloudControllerManagerConfig".into(),
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
                            path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(
                                    serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                        path: "/etc/kubernetes/cloud_ca.crt".to_string(),
                                        owner: Some("root:root".into()),
                                        permissions: Some("0600".to_string()),
                                        encoding: Some(
                                            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64,
                                        ),
                                        content: Some("{{ .cloudCaCert }}".to_string()),
                                        ..Default::default()
                                    }).unwrap(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(
                                    serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                        path: "/etc/kubernetes/cloud.conf".to_string(),
                                        owner: Some("root:root".into()),
                                        permissions: Some("0600".to_string()),
                                        encoding: Some(
                                            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64,
                                        ),
                                        content: Some("{{ .cloudControllerManagerConfig }}".to_string()),
                                        ..Default::default()
                                    }).unwrap(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
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
                            path: "/spec/template/spec/files/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(
                                    serde_yaml::to_string(&KubeadmConfigTemplateTemplateSpecFiles {
                                        path: "/etc/kubernetes/cloud_ca.crt".to_string(),
                                        owner: Some("root:root".into()),
                                        permissions: Some("0600".to_string()),
                                        encoding: Some(
                                            KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64,
                                        ),
                                        content: Some("{{ .cloudCaCert }}".to_string()),
                                        ..Default::default()
                                    }).unwrap(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/files/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(
                                    serde_yaml::to_string(&KubeadmConfigTemplateTemplateSpecFiles {
                                        path: "/etc/kubernetes/cloud.conf".to_string(),
                                        owner: Some("root:root".into()),
                                        permissions: Some("0600".to_string()),
                                        encoding: Some(
                                            KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64,
                                        ),
                                        content: Some("{{ .cloudControllerManagerConfig }}".to_string()),
                                        ..Default::default()
                                    }).unwrap(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                    ],
                },
            ]),
            ..Default::default()
        }]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;
    use indoc::indoc;
    use pretty_assertions::assert_eq;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "cloudCaCert")]
        cloud_ca_cert: CloudCACertificatesConfig,

        #[serde(rename = "cloudControllerManagerConfig")]
        cloud_controller_manager_config: CloudControllerManagerConfig,
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};
        let values = Values {
            cloud_ca_cert: CloudCACertificatesConfig(base64::encode(indoc!(
                r#"
                -----BEGIN CERTIFICATE-----
                MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzZz5z5z5z5z5z5z5z5z
                -----END CERTIFICATE-----
                "#
            ))),
            cloud_controller_manager_config: CloudControllerManagerConfig(base64::encode(indoc!(
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
            ))),
        };

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kcpt_spec = resources.kubeadm_control_plane_template.spec.template.spec;

        let kcpt_files = kcpt_spec
            .kubeadm_config_spec
            .files
            .expect("files should be set");

        let kcpt_ca_file = kcpt_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/cloud_ca.crt")
            .expect("file should be set");
        assert_eq!(
            kcpt_ca_file.path,
            "/etc/kubernetes/cloud_ca.crt"
        );
        assert_eq!(kcpt_ca_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kcpt_ca_file.permissions.as_deref(), Some("0600"));
        assert_eq!(
            kcpt_ca_file.encoding,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kcpt_ca_file.content,
            Some(values.cloud_ca_cert.0.clone())
        );

        let kcpt_ccm_file = kcpt_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/cloud.conf")
            .expect("file should be set");
        assert_eq!(kcpt_ccm_file.path, "/etc/kubernetes/cloud.conf");
        assert_eq!(kcpt_ccm_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kcpt_ccm_file.permissions.as_deref(), Some("0600"));
        assert_eq!(
            kcpt_ccm_file.encoding,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kcpt_ccm_file.content,
            Some(values.cloud_controller_manager_config.0.clone())
        );

        let kct_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("spec should be set");

        let kct_files = kct_spec.files.expect("files should be set");

        let kct_ca_file = kct_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/cloud_ca.crt")
            .expect("file should be set");
        assert_eq!(
            kct_ca_file.path,
            "/etc/kubernetes/cloud_ca.crt"
        );
        assert_eq!(kct_ca_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kct_ca_file.permissions.as_deref(), Some("0600"));
        assert_eq!(
            kct_ca_file.encoding,
            Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kct_ca_file.content,
            Some(values.cloud_ca_cert.0.clone())
        );

        let kct_ccm_file = kct_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/cloud.conf")
            .expect("file should be set");
        assert_eq!(kct_ccm_file.path, "/etc/kubernetes/cloud.conf");
        assert_eq!(kct_ccm_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kct_ccm_file.permissions.as_deref(), Some("0600"));
        assert_eq!(
            kct_ccm_file.encoding,
            Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kct_ccm_file.content,
            Some(values.cloud_controller_manager_config.0.clone())
        );
    }
}
