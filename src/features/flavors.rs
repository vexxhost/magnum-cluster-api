use super::ClusterFeature;
use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources,
            ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
            ClusterClassVariables, ClusterClassVariablesSchema,
        },
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::{ClusterClassVariablesSchemaExt, ClusterFeatureEntry},
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "controlPlaneFlavor")]
pub struct ControlPlaneFlavorConfig(pub String);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "flavor")]
pub struct WorkerFlavorConfig(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            ClusterClassVariables {
                name: "controlPlaneFlavor".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<ControlPlaneFlavorConfig>(),
            },
            ClusterClassVariables {
                name: "flavor".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<WorkerFlavorConfig>(),
            },
        ]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "flavors".into(),
            definitions: Some(vec![
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: OpenStackMachineTemplate::api_resource().api_version,
                        kind: OpenStackMachineTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            control_plane: Some(true),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/flavor".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("controlPlaneFlavor".into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                    ],
                },
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: OpenStackMachineTemplate::api_resource().api_version,
                        kind: OpenStackMachineTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                names: Some(vec!["default-worker".to_string()])
                            }),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/flavor".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("flavor".into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                    ],
                }
            ]),
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
    fn test_patches() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .control_plane_openstack_machine_template
                .spec
                .template
                .spec
                .flavor,
            Some(values.control_plane_flavor.0)
        );

        assert_eq!(
            resources
                .worker_openstack_machine_template
                .spec
                .template
                .spec
                .flavor,
            Some(values.flavor.0)
        );
    }
}
