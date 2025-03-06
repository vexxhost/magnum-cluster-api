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
pub struct APIServerLoadBalancerConfig {
    pub enabled: bool,

    pub provider: String,

    #[builder(default)]
    pub flavor: Option<String>,

    #[builder(default)]
    #[serde(rename = "availabilityZone")]
    pub availability_zone: Option<String>,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "apiServerLoadBalancer")]
    pub api_server_load_balancer: APIServerLoadBalancerConfig,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
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
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches() {
        let feature = Feature {};

        let mut values = default_values();
        values.api_server_load_balancer = APIServerLoadBalancerConfig::builder()
            .enabled(true)
            .provider("octavia".into())
            .flavor(Some("ha".into()))
            .availability_zone(Some("zone-1".into()))
            .build();

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
        assert_eq!(
            api_server_load_balancer.flavor,
            values.api_server_load_balancer.flavor
        );
        assert_eq!(
            api_server_load_balancer.availability_zone,
            values.api_server_load_balancer.availability_zone
        );
    }
}
