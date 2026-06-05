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
        kubeadmconfigtemplates::KubeadmConfigTemplate,
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
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
#[allow(dead_code)]
pub struct FeatureValues {
    /// `kubeletExtraArgs` is a YAML snippet listing additional kubelet flags
    /// supplied by the user via the `kubelet_extra_args` cluster label.
    ///
    /// The value is spliced into the rendered `kubeletExtraArgs` map alongside
    /// the defaults that this feature owns (`cloud-provider` and
    /// `tls-cipher-suites`).  When the label is unset, the variable is the
    /// empty string and only the defaults are emitted.
    ///
    /// Example: `"\nmax-pods: \"150\"\nsystem-reserved: \"cpu=100m,memory=128Mi\""`.
    #[serde(rename = "kubeletExtraArgs")]
    pub kubelet_extra_args: String,
}

pub struct Feature {}

// NOTE: This feature owns the `kubeletExtraArgs` map.  We render the full map
// (including the defaults `cloud-provider: external` and `tls-cipher-suites`)
// so the patch is order-independent: replacing the parent map cannot
// accidentally drop other features' defaults, because they are emitted here
// as well.
const KUBELET_EXTRA_ARGS_TEMPLATE: &str = indoc!(
    r#"
    cloud-provider: external
    tls-cipher-suites: {{ .kubeletTLSCipherSuites }}{{ .kubeletExtraArgs }}"#
);

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "kubeletExtraArgs".into(),
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
                            path: "/spec/template/spec/kubeadmConfigSpec/initConfiguration/nodeRegistration/kubeletExtraArgs".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(KUBELET_EXTRA_ARGS_TEMPLATE.to_string()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/nodeRegistration/kubeletExtraArgs".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(KUBELET_EXTRA_ARGS_TEMPLATE.to_string()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                    ],
                },
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: KubeadmConfigTemplate::api_resource().api_version,
                        kind: KubeadmConfigTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            machine_deployment_class: Some(
                                ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                    names: Some(vec!["default-worker".to_string()]),
                                },
                            ),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/joinConfiguration/nodeRegistration/kubeletExtraArgs".into(),
                        value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                            template: Some(KUBELET_EXTRA_ARGS_TEMPLATE.to_string()),
                            ..Default::default()
                        }),
                        ..Default::default()
                    }],
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
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_with_user_args() {
        let feature = Feature {};

        let mut values = default_values();
        values.kubelet_extra_args = "\nmax-pods: \"150\"\nsystem-reserved: \"cpu=100m,memory=128Mi\"".to_string();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kubeadm_config_spec = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec;

        let expected = btreemap! {
            "cloud-provider".to_string() => "external".to_string(),
            "tls-cipher-suites".to_string() => values.kubelet_tls_cipher_suites.clone(),
            "max-pods".to_string() => "150".to_string(),
            "system-reserved".to_string() => "cpu=100m,memory=128Mi".to_string(),
        };

        assert_eq!(
            kubeadm_config_spec
                .init_configuration
                .expect("init configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            expected,
        );

        assert_eq!(
            kubeadm_config_spec
                .join_configuration
                .expect("join configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            expected,
        );

        assert_eq!(
            resources
                .kubeadm_config_template
                .spec
                .template
                .spec
                .expect("spec should be set")
                .join_configuration
                .expect("join configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            expected,
        );
    }

    #[test]
    fn test_patches_with_empty_user_args() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let expected = btreemap! {
            "cloud-provider".to_string() => "external".to_string(),
            "tls-cipher-suites".to_string() => values.kubelet_tls_cipher_suites.clone(),
        };

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .init_configuration
                .expect("init configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .kubelet_extra_args
                .expect("kubelet extra args should be set"),
            expected,
        );
    }
}
