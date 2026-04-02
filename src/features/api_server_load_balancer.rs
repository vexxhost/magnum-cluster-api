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

/// Schema helper: emit `{"type":"string"}` for an optional string field.
///
/// CAPI's admission webhook uses Go's `JSONSchemaProps.Type` which is a plain
/// `string`, not a `[]string`.  The default schemars derivation for
/// `Option<String>` produces `"type": ["string", "null"]` (an array), which
/// the Go JSON unmarshaller rejects with "cannot unmarshal array into Go struct
/// field … of type string".  Using this helper keeps the field out of the
/// schema's `required` array (via `#[serde(default)]`) while generating a
/// plain `"type": "string"` that CAPI accepts.
fn optional_string_schema(_: &mut schemars::gen::SchemaGenerator) -> schemars::schema::Schema {
    schemars::schema::Schema::Object(schemars::schema::SchemaObject {
        instance_type: Some(schemars::schema::InstanceType::String.into()),
        ..Default::default()
    })
}

#[derive(Clone, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct APIServerLoadBalancerConfig {
    pub enabled: bool,

    #[serde(default, skip_serializing_if = "Option::is_none")]
    #[schemars(schema_with = "optional_string_schema")]
    #[builder(default)]
    pub provider: Option<String>,

    #[serde(default, skip_serializing_if = "str::is_empty")]
    #[builder(default)]
    pub flavor: String,

    #[serde(default, skip_serializing_if = "str::is_empty", rename = "availabilityZone")]
    #[builder(default)]
    pub availability_zone: String,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
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
            .provider(Some("octavia".to_string()))
            .flavor("ha".to_string())
            .availability_zone("zone-1".to_string())
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
            values.api_server_load_balancer.provider
        );
        assert_eq!(
            api_server_load_balancer.flavor,
            Some(values.api_server_load_balancer.flavor)
        );
        assert_eq!(
            api_server_load_balancer.availability_zone,
            Some(values.api_server_load_balancer.availability_zone)
        );
    }

    #[test]
    fn test_patches_with_none_values() {
        let feature = Feature {};

        let mut values = default_values();
        values.api_server_load_balancer = APIServerLoadBalancerConfig::builder()
            .enabled(true)
            .provider(Some("octavia".to_string()))
            .flavor("".to_string())
            .availability_zone("".to_string())
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
            values.api_server_load_balancer.provider
        );
        assert_eq!(api_server_load_balancer.flavor, None);
        assert_eq!(api_server_load_balancer.availability_zone, None);
    }

    #[test]
    fn test_schema_provider_is_optional_string() {
        use crate::features::ClusterClassVariablesSchemaExt;

        let schema = ClusterClassVariablesSchema::from_object::<APIServerLoadBalancerConfig>();
        let v: serde_json::Value = serde_json::from_str(
            &serde_json::to_string(&schema.open_apiv3_schema).unwrap(),
        )
        .unwrap();

        // provider must NOT be in required (field is optional)
        let required = v.get("required").and_then(|r| r.as_array());
        if let Some(req) = required {
            assert!(
                !req.iter().any(|r| r.as_str() == Some("provider")),
                "provider should not be in required"
            );
        }

        // provider.type must be a plain string "string", not an array
        let provider_type = &v["properties"]["provider"]["type"];
        assert_eq!(
            provider_type,
            "string",
            "provider type must be a plain string (CAPI rejects arrays)"
        );
    }

    #[test]
    fn test_patches_without_provider() {
        let feature = Feature {};

        let mut values = default_values();
        values.api_server_load_balancer = APIServerLoadBalancerConfig::builder()
            .enabled(true)
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

        assert_eq!(api_server_load_balancer.enabled, true);
        assert_eq!(api_server_load_balancer.provider, None);
        assert_eq!(api_server_load_balancer.flavor, None);
        assert_eq!(api_server_load_balancer.availability_zone, None);
    }
}
