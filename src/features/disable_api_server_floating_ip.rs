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

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
pub struct Config(pub bool);

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "disableAPIServerFloatingIP")]
    pub disable_api_server_floating_ip: Config,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "disableAPIServerFloatingIP".into(),
            enabled_if: Some("{{ if .disableAPIServerFloatingIP }}true{{end}}".into()),
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
                    path: "/spec/template/spec/disableAPIServerFloatingIP".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        variable: Some("disableAPIServerFloatingIP".into()),
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
    use crate::features::test::{default_values, TestClusterResources};
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_if_enabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.disable_api_server_floating_ip = Config(true);

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .disable_api_server_floating_ip,
            Some(true)
        );
    }

    #[test]
    fn test_patches_if_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.disable_api_server_floating_ip = Config(false);

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .disable_api_server_floating_ip,
            None
        );
    }
}
