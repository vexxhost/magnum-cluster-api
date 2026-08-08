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
    #[serde(rename = "apiServerFixedIP")]
    pub api_server_fixed_ip: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "apiServerFixedIP".into(),
            enabled_if: Some("{{ if .apiServerFixedIP }}true{{end}}".into()),
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
