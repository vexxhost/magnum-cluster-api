use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources,
        },
        openstackclustertemplates::OpenStackClusterTemplate,
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables, ClusterClassVariables, ClusterClassVariablesSchema,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "apiServerFixedIP", default)]
    pub api_server_fixed_ip: String,

    /// Gates the patch so an existing immutable CAPO field remains rendered
    /// even when a later Magnum update omits the label.
    #[serde(rename = "apiServerFixedIPManaged", default)]
    pub api_server_fixed_ip_managed: bool,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "apiServerFixedIP".into(),
            enabled_if: Some("{{ if .apiServerFixedIPManaged }}true{{end}}".into()),
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
                    path: "/spec/template/spec/apiServerFixedIP".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        variable: Some("apiServerFixedIP".into()),
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
    fn patches_a_managed_fixed_ip() {
        let mut values = default_values();
        values.api_server_fixed_ip = "10.20.8.70".into();
        values.api_server_fixed_ip_managed = true;

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&Feature {}.patches(), &values);

        assert_eq!(
            resources.openstack_cluster_template.spec.template.spec.api_server_fixed_ip,
            Some("10.20.8.70".into())
        );
    }

    #[test]
    fn omits_an_unmanaged_fixed_ip() {
        let mut values = default_values();
        values.api_server_fixed_ip = "10.20.8.70".into();
        values.api_server_fixed_ip_managed = false;

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&Feature {}.patches(), &values);

        assert_eq!(
            resources.openstack_cluster_template.spec.template.spec.api_server_fixed_ip,
            None
        );
    }
}
