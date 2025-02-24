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
#[serde(rename_all = "lowercase")]
pub enum OperatingSystem {
    Ubuntu,
    Flatcar,
}

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[schemars(with = "string")]
pub struct AptProxyConfig(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            ClusterClassVariables {
                name: "operatingSystem".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<OperatingSystem>(),
            },
            ClusterClassVariables {
                name: "aptProxyConfig".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<AptProxyConfig>(),
            },
        ]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "ubuntu".into(),
                enabled_if: Some(r#"{{ if eq .operatingSystem "ubuntu" }}true{{end}}"#.into()),
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
                                            path: "/etc/apt/apt.conf.d/90proxy".to_string(),
                                            owner: Some("root:root".into()),
                                            permissions: Some("0644".to_string()),
                                            encoding: Some(
                                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64,
                                            ),
                                            content: Some("{{ .aptProxyConfig }}".to_string()),
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
                                            path: "/etc/apt/apt.conf.d/90proxy".to_string(),
                                            owner: Some("root:root".into()),
                                            permissions: Some("0644".to_string()),
                                            encoding: Some(
                                                KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64,
                                            ),
                                            content: Some("{{ .aptProxyConfig }}".to_string()),
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
            }
        ]
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
        #[serde(rename = "operatingSystem")]
        operating_system: OperatingSystem,

        #[serde(rename = "aptProxyConfig")]
        apt_proxy_config: AptProxyConfig,
    }

    #[test]
    fn test_apply_patches_for_ubuntu() {
        let feature = Feature {};
        let values = Values {
            operating_system: OperatingSystem::Ubuntu,
            apt_proxy_config: AptProxyConfig(base64::encode(indoc!(
                "
                Acquire::http::Proxy \"http://proxy.example.com\";
                Acquire::https::Proxy \"http://proxy.example.com\";
                "
            ))),
        };

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kcpt_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("files should be set");

        let kcpt_proxy_file = kcpt_files
            .iter()
            .find(|f| f.path == "/etc/apt/apt.conf.d/90proxy")
            .expect("file should be set");
        assert_eq!(kcpt_proxy_file.path, "/etc/apt/apt.conf.d/90proxy");
        assert_eq!(kcpt_proxy_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kcpt_proxy_file.permissions.as_deref(), Some("0644"));
        assert_eq!(
            kcpt_proxy_file.encoding,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kcpt_proxy_file.content,
            Some(values.apt_proxy_config.0.clone())
        );

        let kct_files = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("spec should be set")
            .files
            .expect("files should be set");

        let kct_proxy_file = kct_files
            .iter()
            .find(|f| f.path == "/etc/apt/apt.conf.d/90proxy")
            .expect("file should be set");
        assert_eq!(kct_proxy_file.path, "/etc/apt/apt.conf.d/90proxy");
        assert_eq!(kct_proxy_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kct_proxy_file.permissions.as_deref(), Some("0644"));
        assert_eq!(
            kct_proxy_file.encoding,
            Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kct_proxy_file.content,
            Some(values.apt_proxy_config.0.clone())
        );
    }
}
