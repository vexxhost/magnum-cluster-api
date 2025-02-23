use super::ClusterFeature;
use crate::{cluster_api::kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate, features::ClusterClassVariablesSchemaExt};
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
    ClusterClassVariablesSchema,
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
pub struct Config {
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

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![ClusterClassVariables {
            name: "openidConnect".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema::from_object::<Config>(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::KCPT_WIP;
    use crate::features::test::{
        assert_subset_of_btreemap, ApplyPatch, ClusterClassPatchEnabled, ToPatch,
    };
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "openidConnect")]
        openid_connect: Config,
    }

    #[test]
    fn test_disabled_if_issuer_is_empty() {
        let feature = Feature {};
        let values = Values {
            openid_connect: Config {
                issuer_url: "".to_string(),
                client_id: "client-id".to_string(),
                username_claim: "email".to_string(),
                username_prefix: "email:".to_string(),
                groups_claim: "groups".to_string(),
                groups_prefix: "groups:".to_string(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, false);
    }

    #[test]
    fn test_enabled_if_issuer_is_set() {
        let feature = Feature {};
        let values = Values {
            openid_connect: Config {
                issuer_url: "https://example.com".to_string(),
                client_id: "client-id".to_string(),
                username_claim: "email".to_string(),
                username_prefix: "email:".to_string(),
                groups_claim: "groups".to_string(),
                groups_prefix: "groups:".to_string(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, true);
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};
        let values = Values {
            openid_connect: Config {
                issuer_url: "https://example.com".to_string(),
                client_id: "client-id".to_string(),
                username_claim: "email".to_string(),
                username_prefix: "email:".to_string(),
                groups_claim: "groups".to_string(),
                groups_prefix: "groups:".to_string(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values.clone());

        assert_eq!(is_enabled, true);

        let mut kcpt = KCPT_WIP.clone();

        // TODO: create a trait that will take kcp, etc and apply the patches
        patch
            .definitions
            .as_ref()
            .expect("definitions should be set")
            .into_iter()
            .for_each(|definition| {
                let p = definition.json_patches.clone().to_patch(&values);
                kcpt.apply_patch(&p);
            });

        assert_subset_of_btreemap(
            &btreemap! {
                "oidc-issuer-url".to_string() => values.openid_connect.issuer_url.to_string(),
                "oidc-client-id".to_string() => values.openid_connect.client_id.to_string(),
                "oidc-username-claim".to_string() => values.openid_connect.username_claim.to_string(),
                "oidc-username-prefix".to_string() => values.openid_connect.username_prefix.to_string(),
                "oidc-groups-claim".to_string() => values.openid_connect.groups_claim.to_string(),
                "oidc-groups-prefix".to_string() => values.openid_connect.groups_prefix.to_string(),
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
