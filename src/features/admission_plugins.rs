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
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "admissionControlList")]
    pub admission_control_list: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "admissionControlList".into(),
            enabled_if: Some("{{ if .admissionControlList }}true{{end}}".into()),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector {
                    api_version: KubeadmControlPlaneTemplate::api_resource().api_version,
                    kind: KubeadmControlPlaneTemplate::api_resource().kind,
                    match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                        control_plane: Some(true),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/enable-admission-plugins".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        variable: Some("admissionControlList".into()),
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
    use crate::{features::test::TestClusterResources, resources::fixtures::default_values};
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled_if_admission_control_list_is_empty() {
        let feature = Feature {};
        let mut values = default_values();
        values.admission_control_list = "".to_string();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        // Should only have the default extra_args, not admission plugins
        assert_eq!(
            &btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "profiling".to_string() => "false".to_string(),
            },
            &resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .cluster_configuration
                .expect("cluster configuration should be set")
                .api_server
                .expect("api server should be set")
                .extra_args
                .expect("extra args should be set")
        );
    }

    #[test]
    fn test_admission_plugins_patch() {
        let feature = Feature {};
        let mut values = default_values();
        values.admission_control_list = "PodNodeSelector,NodeRestriction".to_string();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        // Verify the admission plugins are set correctly
        let cluster_configuration = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .expect("cluster configuration should be set");

        let api_server = cluster_configuration
            .api_server
            .expect("api server should be set");

        let extra_args = api_server.extra_args.expect("extra args should be set");

        assert_eq!(
            extra_args.get("enable-admission-plugins"),
            Some(&"PodNodeSelector,NodeRestriction".to_string())
        );

        // Also verify the default args are still present
        assert_eq!(
            extra_args.get("cloud-provider"),
            Some(&"external".to_string())
        );
        assert_eq!(extra_args.get("profiling"), Some(&"false".to_string()));
    }

    #[test]
    fn test_variables() {
        let feature = Feature {};
        let variables = feature.variables();

        assert_eq!(variables.len(), 1);
        assert_eq!(variables[0].name, "admissionControlList");
        assert_eq!(variables[0].required, true);
    }

    #[test]
    fn test_default_node_restriction_only() {
        let feature = Feature {};
        let mut values = default_values();
        values.admission_control_list = "NodeRestriction".to_string();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let extra_args = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .expect("cluster configuration should be set")
            .api_server
            .expect("api server should be set")
            .extra_args
            .expect("extra args should be set");

        assert_eq!(
            extra_args.get("enable-admission-plugins"),
            Some(&"NodeRestriction".to_string())
        );
    }

    #[test]
    fn test_multiple_admission_plugins() {
        let feature = Feature {};
        let mut values = default_values();
        values.admission_control_list = "PodNodeSelector,NodeRestriction,LimitRanger".to_string();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let extra_args = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .expect("cluster configuration should be set")
            .api_server
            .expect("api server should be set")
            .extra_args
            .expect("extra args should be set");

        assert_eq!(
            extra_args.get("enable-admission-plugins"),
            Some(&"PodNodeSelector,NodeRestriction,LimitRanger".to_string())
        );
    }
}
