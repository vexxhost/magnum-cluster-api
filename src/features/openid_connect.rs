use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
            ClusterClassVariablesSchema,
        },
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use typed_builder::TypedBuilder;

#[derive(Clone, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct OpenIdConnectConfig {
    #[serde(rename = "issuerUrl")]
    pub issuer_url: String,

    #[serde(rename = "clientId")]
    pub client_id: String,

    #[serde(rename = "usernameClaim")]
    pub username_claim: String,

    #[serde(rename = "usernamePrefix")]
    pub username_prefix: String,

    #[serde(rename = "groupsClaim")]
    pub groups_claim: String,

    #[serde(rename = "groupsPrefix")]
    pub groups_prefix: String,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "openidConnect")]
    pub openid_connect: OpenIdConnectConfig,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "openidConnect".into(),
                enabled_if: Some("{{ if .openidConnect.issuerUrl }}true{{end}}".into()),
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

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::resources::fixtures::default_values;
    use crate::features::test::TestClusterResources;
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled_if_issuer_is_empty() {
        let feature = Feature {};

        let mut values = default_values();
        values.openid_connect = OpenIdConnectConfig::builder()
            .issuer_url("".to_string())
            .client_id("client-id".to_string())
            .username_claim("email".to_string())
            .username_prefix("email:".to_string())
            .groups_claim("groups".to_string())
            .groups_prefix("groups:".to_string())
            .build();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            &btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "profiling".to_string() => "false".to_string(),
            },
            &resources
                .kubeadm_control_plane_template
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

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};

        let mut values = default_values();
        values.openid_connect = OpenIdConnectConfig::builder()
            .issuer_url("https://example.com".to_string())
            .client_id("client-id".to_string())
            .username_claim("email".to_string())
            .username_prefix("email:".to_string())
            .groups_claim("groups".to_string())
            .groups_prefix("groups:".to_string())
            .build();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            &btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "oidc-client-id".to_string() => values.openid_connect.client_id.to_string(),
                "oidc-groups-claim".to_string() => values.openid_connect.groups_claim.to_string(),
                "oidc-groups-prefix".to_string() => values.openid_connect.groups_prefix.to_string(),
                "oidc-issuer-url".to_string() => values.openid_connect.issuer_url.to_string(),
                "oidc-username-claim".to_string() => values.openid_connect.username_claim.to_string(),
                "oidc-username-prefix".to_string() => values.openid_connect.username_prefix.to_string(),
                "profiling".to_string() => "false".to_string(),
            },
            &resources
                .kubeadm_control_plane_template
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
