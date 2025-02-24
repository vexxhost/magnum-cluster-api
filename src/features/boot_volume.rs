use super::ClusterFeature;
use crate::{
    cluster_api::openstackmachinetemplates::OpenStackMachineTemplate,
    features::ClusterClassVariablesSchemaExt,
};
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources,
    ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
    ClusterClassVariables, ClusterClassVariablesSchema,
};
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
pub struct Config {
    pub r#type: String,
    pub size: i64,
}

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![ClusterClassVariables {
            name: "bootVolume".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema::from_object::<Config>(),
        }]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "bootVolume".into(),
            enabled_if: Some("{{ if gt .bootVolume.size 0.0 }}true{{end}}".into()),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector {
                    api_version: OpenStackMachineTemplate::api_resource().api_version,
                    kind: OpenStackMachineTemplate::api_resource().kind,
                    match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                        control_plane: Some(true),
                        machine_deployment_class: Some(
                            ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                names: Some(vec!["control-plane".into()]),
                                ..Default::default()
                            }
                        ),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/rootVolume".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(indoc!("
                            type: {{ .bootVolume.type }}
                            sizeGiB: {{ .bootVolume.size }}").to_string(),
                        ),
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
    use super::*;
    use crate::{
        cluster_api::openstackmachinetemplates::OpenStackMachineTemplateTemplateSpecRootVolume,
        features::test::TestClusterResources,
    };

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "bootVolume")]
        boot_volume: Config,
    }

    #[test]
    fn test_enabled() {
        let feature = Feature {};
        let values = Values {
            boot_volume: Config {
                r#type: "ssd".into(),
                size: 10,
            },
        };

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .control_plane_openstack_machine_template
                .spec
                .template
                .spec
                .root_volume,
            Some(OpenStackMachineTemplateTemplateSpecRootVolume {
                r#type: Some(values.boot_volume.r#type),
                size_gi_b: values.boot_volume.size,
                ..Default::default()
            })
        );
    }

    #[test]
    fn test_disabled() {
        let feature = Feature {};
        let values = Values {
            boot_volume: Config {
                r#type: "ssd".into(),
                size: 0,
            },
        };

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .control_plane_openstack_machine_template
                .spec
                .template
                .spec
                .root_volume,
            None
        );
    }
}
