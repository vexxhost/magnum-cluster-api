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
        openstackmachinetemplates::{
            OpenStackMachineTemplate, OpenStackMachineTemplateTemplateSpecServerGroup,
        },
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use indoc::indoc;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "serverGroupId")]
    pub server_group_id: String,

    #[serde(rename = "isServerGroupDiffFailureDomain")]
    pub is_server_group_diff_failure_domain: bool,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "serverGroupId".into(),
            definitions: Some(vec![
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: OpenStackMachineTemplate::api_resource().api_version,
                        kind: OpenStackMachineTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            control_plane: Some(true),
                            machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                names: Some(vec!["default-worker".to_string()])
                            }),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/serverGroup".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(
                                    serde_yaml::to_string(
                                        &OpenStackMachineTemplateTemplateSpecServerGroup {
                                            id: Some("{{ .serverGroupId }}".to_string()),
                                            ..Default::default()
                                        },
                                    )
                                    .unwrap(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/schedulerHintAdditionalProperties".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(indoc!("
                                    - name: different_failure_domain
                                      value:
                                        type: Bool
                                        bool: {{ .isServerGroupDiffFailureDomain }}").to_string(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        }
                    ],
                },
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
    use crate::{
        cluster_api::openstackmachinetemplates::{
            OpenStackMachineTemplateTemplateSpecSchedulerHintAdditionalProperties,
            OpenStackMachineTemplateTemplateSpecSchedulerHintAdditionalPropertiesValue,
            OpenStackMachineTemplateTemplateSpecSchedulerHintAdditionalPropertiesValueType,
        },
        features::test::TestClusterResources,
        resources::fixtures::default_values,
    };
    use pretty_assertions::assert_eq;

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let templates = vec![
            &resources.control_plane_openstack_machine_template,
            &resources.worker_openstack_machine_template,
        ];

        for template in templates {
            let spec = &template.spec.template.spec;

            assert_eq!(
                spec.server_group,
                Some(OpenStackMachineTemplateTemplateSpecServerGroup {
                    id: Some(values.server_group_id.clone()),
                    ..Default::default()
                })
            );
            assert_eq!(
                spec.scheduler_hint_additional_properties,
                Some(vec![
                    OpenStackMachineTemplateTemplateSpecSchedulerHintAdditionalProperties {
                        name: "different_failure_domain".to_string(),
                        value: OpenStackMachineTemplateTemplateSpecSchedulerHintAdditionalPropertiesValue {
                            r#type: OpenStackMachineTemplateTemplateSpecSchedulerHintAdditionalPropertiesValueType::Bool,
                            bool: Some(values.is_server_group_diff_failure_domain),
                            ..Default::default()
                        },
                    }
                ])
            );
        }
    }
}
