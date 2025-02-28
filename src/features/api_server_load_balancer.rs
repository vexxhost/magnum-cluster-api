use super::ClusterFeature;
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
        openstackclustertemplates::OpenStackClusterTemplate,
    },
    features::{ClusterClassVariablesSchemaExt, ClusterFeatureEntry},
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use typed_builder::TypedBuilder;

#[derive(Clone, Serialize, Deserialize, JsonSchema, TypedBuilder)]
#[serde(rename = "apiServerLoadBalancer")]
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

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::default_values;
    use crate::features::test::TestClusterResources;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let api_server_load_balancer = resources
            .openstack_cluster_template
            .spec
            .template
            .spec
            .api_server_load_balancer
            .expect("apiServerLoadBalancer should be set");

        assert_eq!(
            api_server_load_balancer.enabled,
            values.api_server_load_balancer.enabled
        );
        assert_eq!(
            api_server_load_balancer.provider,
            Some(values.api_server_load_balancer.provider)
        );
    }
}
