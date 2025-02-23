use super::ClusterFeature;
use crate::{
    cluster_api::openstackclustertemplates::OpenStackClusterTemplate,
    features::ClusterClassVariablesSchemaExt,
};
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
    pub enabled: bool,
    pub provider: String,
}

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![ClusterClassVariables {
            name: "apiServerLoadBalancer".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema::from_object::<Config>(),
        }]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "apiServerLoadBalancer".into(),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector {
                    api_version: OpenStackClusterTemplate::api_resource().api_version,
                    kind: OpenStackClusterTemplate::api_resource().kind,
                    match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                        infrastructure_cluster: Some(true),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/apiServerLoadBalancer".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        variable: Some("apiServerLoadBalancer".into()),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
            }]),
            ..Default::default()
        }]
    }
}

#[cfg(test)]
mod tests {
    use crate::features::test::{ApplyPatch, ToPatch, OCT_WIP};

    use super::*;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "apiServerLoadBalancer")]
        api_server_load_balancer: Config,
    }

    #[test]
    fn test_patches() {
        let feature = Feature {};
        let values = Values {
            api_server_load_balancer: Config {
                enabled: true,
                provider: "amphora".into(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");

        let mut oct = OCT_WIP.clone();

        // TODO: create a trait that will take kcp, etc and apply the patches
        patch
            .definitions
            .as_ref()
            .expect("definitions should be set")
            .into_iter()
            .for_each(|definition| {
                let p = definition.json_patches.clone().to_patch(&values);
                oct.apply_patch(&p);
            });

        let api_server_load_balancer = oct
            .spec
            .template
            .spec
            .api_server_load_balancer
            .expect("apiServerLoadBalancer should be set");

        assert_eq!(api_server_load_balancer.enabled, true);
        assert_eq!(api_server_load_balancer.provider, Some("amphora".to_string()));
    }
}
