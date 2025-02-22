use super::ClusterFeature;
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
    ClusterClassVariablesSchema, ClusterClassVariablesSchemaOpenApiv3Schema,
};
use maplit::btreemap;
use serde_json::json;

pub struct OpenIdConnectFeature {}

impl ClusterFeature for OpenIdConnectFeature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        let default_string_schema = ClusterClassVariablesSchemaOpenApiv3Schema {
            r#type: Some("string".into()),
            ..Default::default()
        };

        vec![ClusterClassVariables {
            name: "openidConnect".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema {
                open_apiv3_schema: ClusterClassVariablesSchemaOpenApiv3Schema {
                    r#type: Some("object".into()),
                    required: Some(vec![
                        "issuerUrl".into(),
                        "clientId".into(),
                        "usernameClaim".into(),
                        "usernamePrefix".into(),
                        "groupsClaim".into(),
                        "groupsPrefix".into(),
                    ]),
                    properties: Some(json!(btreemap! {
                        "issuerUrl".to_string() => default_string_schema.clone(),
                        "clientId".to_string() => default_string_schema.clone(),
                        "usernameClaim".to_string() => default_string_schema.clone(),
                        "usernamePrefix".to_string() => default_string_schema.clone(),
                        "groupsClaim".to_string() => default_string_schema.clone(),
                        "groupsPrefix".to_string() => default_string_schema.clone(),
                    })),
                    ..Default::default()
                },
            },
        }]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "openidConnect".into(),
                enabled_if: Some("{{ if .openidConnect.issuerUrl }}true{{end}}".into()),
                definitions: Some(vec![
                    ClusterClassPatchesDefinitions {
                        selector: ClusterClassPatchesDefinitionsSelector {
                            // TODO: detect this from the kubeadmcontrolplanetemplates module
                            api_version: "controlplane.cluster.x-k8s.io/v1beta1".into(),
                            kind: "KubeadmControlPlaneTemplate".into(),
                            match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                                control_plane: Some(true),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-issuer-url".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("openidConnect.issuerUrl".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-client-id".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("openidConnect.clientId".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-username-claim".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("openidConnect.usernameClaim".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-username-prefix".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("openidConnect.usernamePrefix".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-groups-claim".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("openidConnect.groupsClaim".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-groups-prefix".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("openidConnect.groupsPrefix".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                        ],
                    }
                ]),
                ..Default::default()
            }
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cluster_api::kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate, KubeadmControlPlaneTemplateSpec,
            KubeadmControlPlaneTemplateTemplate, KubeadmControlPlaneTemplateTemplateSpec,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer,
        },
        features::test::{assert_subset_of_btreemap, ApplyPatch, ToPatch, ClusterClassPatchEnabled},
    };
    use maplit::hashmap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled_if_issuer_is_empty() {
        let feature = OpenIdConnectFeature {};
        let values = hashmap! {
            "openidConnect".to_string() => hashmap! {
                "issuerUrl".to_string() => "",
            }
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, false);
    }

    #[test]
    fn test_enabled_if_issuer_is_set() {
        let feature = OpenIdConnectFeature {};
        let values = hashmap! {
            "openidConnect".to_string() => hashmap! {
                "issuerUrl".to_string() => "https://example.com",
            }
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, true);
    }

    #[test]
    fn test_apply_patches() {
        let feature = OpenIdConnectFeature {};
        let values = hashmap! {
            "openidConnect".to_string() => hashmap! {
                "issuerUrl".to_string() => "https://example.com",
                "clientId".to_string() => "client-id",
                "usernameClaim".to_string() => "email",
                "usernamePrefix".to_string() => "email:",
                "groupsClaim".to_string() => "groups",
                "groupsPrefix".to_string() => "groups:",
            }
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values.clone());

        assert_eq!(is_enabled, true);

        // TODO: move this out since this is generic/standard
        let mut kcpt = KubeadmControlPlaneTemplate {
            metadata: Default::default(),
            spec: KubeadmControlPlaneTemplateSpec {
                template: KubeadmControlPlaneTemplateTemplate {
                    spec: KubeadmControlPlaneTemplateTemplateSpec {
                        kubeadm_config_spec: KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec {
                            cluster_configuration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration {
                                api_server: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer {
                                    extra_args: Some({
                                        btreemap! {
                                            "cloud-provider".to_string() => "external".to_string(),
                                            "profiling".to_string() => "false".to_string(),
                                        }
                                    }),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ..Default::default()
                    },
                    ..Default::default()
                },
                ..Default::default()
            }
        };

        // TODO: create a trait that will take kcp, etc and apply the patches
        patch
            .definitions
            .as_ref()
            .expect("definitions should be set")
            .into_iter()
            .for_each(|definition| {
                let p = definition.json_patches.clone().to_patch(values.clone());
                kcpt.apply_patch(&p);
            });

        assert_subset_of_btreemap(
            &btreemap! {
                "oidc-issuer-url".to_string() => values["openidConnect"]["issuerUrl"].to_string(),
                "oidc-client-id".to_string() => values["openidConnect"]["clientId"].to_string(),
                "oidc-username-claim".to_string() => values["openidConnect"]["usernameClaim"].to_string(),
                "oidc-username-prefix".to_string() => values["openidConnect"]["usernamePrefix"].to_string(),
                "oidc-groups-claim".to_string() => values["openidConnect"]["groupsClaim"].to_string(),
                "oidc-groups-prefix".to_string() => values["openidConnect"]["groupsPrefix"].to_string(),
            },
            &kcpt
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .cluster_configuration
                .expect("cluster_configuration should be set")
                .api_server
                .expect("api_server should be set")
                .extra_args
                .expect("extra_args should be set"),
        );
    }
}
