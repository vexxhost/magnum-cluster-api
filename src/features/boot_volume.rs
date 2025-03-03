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
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use typed_builder::TypedBuilder;

#[derive(Clone, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct BootVolumeConfig {
    pub r#type: String,
    pub size: i64,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "bootVolume")]
    pub boot_volume: BootVolumeConfig,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
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
                                names: Some(vec!["default-worker".into()]),
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

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cluster_api::openstackmachinetemplates::OpenStackMachineTemplateTemplateSpecRootVolume,
        features::test::TestClusterResources, resources::fixtures::default_values,
    };
    use pretty_assertions::assert_eq;

    #[test]
    fn test_enabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.boot_volume = BootVolumeConfig::builder()
            .r#type("ssd".into())
            .size(10)
            .build();

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
                r#type: Some(values.clone().boot_volume.r#type),
                size_gi_b: values.clone().boot_volume.size,
                ..Default::default()
            })
        );

        assert_eq!(
            resources
                .worker_openstack_machine_template
                .spec
                .template
                .spec
                .root_volume,
            Some(OpenStackMachineTemplateTemplateSpecRootVolume {
                r#type: Some(values.clone().boot_volume.r#type),
                size_gi_b: values.clone().boot_volume.size,
                ..Default::default()
            })
        );
    }

    #[test]
    fn test_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.boot_volume = BootVolumeConfig::builder()
            .r#type("ssd".into())
            .size(0)
            .build();

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
