use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches, ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
        },
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
    },
    features::{ClusterFeatureEntry, ClusterFeaturePatches, ClusterFeatureVariables},
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "cloudProvider".into(),
                enabled_if: Some(r#"{{ semverCompare "<1.29.0" .builtin.controlPlane.version }}"#.into()),
                definitions: Some(vec![
                    ClusterClassPatchesDefinitions {
                        selector: ClusterClassPatchesDefinitionsSelector {
                            api_version: KubeadmControlPlaneTemplate::api_resource().api_version,
                            kind: KubeadmControlPlaneTemplate::api_resource().kind,
                            match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                                control_plane: Some(true),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/cloud-provider".into(),
                                value: Some("external".into()),
                                ..Default::default()
                            },
                        ],
                    }

                ]),
                ..Default::default()
            }
        ]
    }
}

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{features::test::TestClusterResources, resources::fixtures::default_values};
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.version = "v1.29.0".to_string();
        resources.apply_patches(&patches, &values);

        let api_server = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .expect("cluster_configuration should be set")
            .api_server
            .expect("api_server should be set");

        assert_eq!(
            &btreemap! {
                "profiling".to_string() => "false".to_string(),
            },
            &api_server.extra_args.expect("extra_args should be set"),
        );
    }

    #[test]
    fn test_enabled() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.version = "v1.28.0".to_string();
        resources.apply_patches(&patches, &values);

        let api_server = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .expect("cluster_configuration should be set")
            .api_server
            .expect("api_server should be set");

        assert_eq!(
            &btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "profiling".to_string() => "false".to_string(),
            },
            &api_server.extra_args.expect("extra_args should be set"),
        );
    }
}
