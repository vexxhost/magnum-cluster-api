// Enable kubelet serving TLS (serverTLSBootstrap): kubelet requests a cluster CA–signed
// serving certificate; API server verifies it when connecting to the kubelet.
//
// Uses kubeadm's native patch mechanism (patches.directory) so that
// serverTLSBootstrap is applied *before* kubelet starts — no post-kubeadm
// sed hacks or kubelet restarts needed.
//
// See: https://github.com/vexxhost/magnum-cluster-api/issues/365

use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources,
            ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
            ClusterClassVariables, ClusterClassVariablesSchema,
        },
        kubeadmconfigtemplates::{KubeadmConfigTemplate, KubeadmConfigTemplateTemplateSpecFiles},
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles,
        },
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    /// Optional so pre-existing clusters without this variable continue to reconcile.
    #[serde(rename = "enableKubeletServingTLS")]
    #[cluster_feature(required = false)]
    pub enable_kubelet_serving_tls: bool,
}

pub struct Feature {}

/// Strategic-merge patch applied by kubeadm to KubeletConfiguration.
const KUBELET_CONFIG_PATCH: &str = r#"{"apiVersion":"kubelet.config.k8s.io/v1beta1","kind":"KubeletConfiguration","serverTLSBootstrap":true}"#;

/// Directory where kubeadm looks for component patches during init/join.
const PATCHES_DIR: &str = "/etc/kubernetes/patches";

/// Patch file name: target=kubeletconfiguration, suffix=0, patchtype=strategic, ext=json.
const PATCH_FILE: &str = "/etc/kubernetes/patches/kubeletconfiguration0+strategic.json";

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "kubeletServingTLS".into(),
            enabled_if: Some("{{ if .enableKubeletServingTLS }}true{{end}}".into()),
            definitions: Some(vec![
                // ── Control-plane nodes ──────────────────────────────────────
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
                        // API server verifies kubelet serving certificates using the cluster CA.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/kubelet-certificate-authority".into(),
                            value: Some(json!("/etc/kubernetes/pki/ca.crt")),
                            ..Default::default()
                        },
                        // Inject the kubelet config strategic-merge patch file.
                        // kubelet-csr-approver is installed via ClusterResourceSet (LegacyClusterResourcesSecret) like CCM/CSI.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                            value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                path: PATCH_FILE.into(),
                                owner: Some("root:root".into()),
                                permissions: Some("0644".into()),
                                content: Some(KUBELET_CONFIG_PATCH.into()),
                                ..Default::default()
                            })),
                            ..Default::default()
                        },
                        // Tell kubeadm init to apply patches from the directory.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/initConfiguration/patches".into(),
                            value: Some(json!({"directory": PATCHES_DIR})),
                            ..Default::default()
                        },
                        // Tell kubeadm join (additional control-plane nodes) to apply patches.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/patches".into(),
                            value: Some(json!({"directory": PATCHES_DIR})),
                            ..Default::default()
                        },
                    ],
                },
                // ── Worker nodes ─────────────────────────────────────────────
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
                    json_patches: vec![
                        // Inject the same kubelet config patch file for workers.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/files/-".into(),
                            value: Some(json!(KubeadmConfigTemplateTemplateSpecFiles {
                                path: PATCH_FILE.into(),
                                owner: Some("root:root".into()),
                                permissions: Some("0644".into()),
                                content: Some(KUBELET_CONFIG_PATCH.into()),
                                ..Default::default()
                            })),
                            ..Default::default()
                        },
                        // Tell kubeadm join on workers to apply patches.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/joinConfiguration/patches".into(),
                            value: Some(json!({"directory": PATCHES_DIR})),
                            ..Default::default()
                        },
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
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_when_enabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_kubelet_serving_tls = true;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        // API server extra arg should be set.
        let api_server = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .as_ref()
            .expect("cluster configuration should be set")
            .api_server
            .as_ref()
            .expect("api server should be set");

        assert_eq!(
            api_server
                .extra_args
                .as_ref()
                .and_then(|m| m.get("kubelet-certificate-authority")),
            Some(&"/etc/kubernetes/pki/ca.crt".to_string())
        );

        // Control-plane: kubelet config patch file should be injected.
        let cp_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .as_ref()
            .expect("control plane files should be set");

        assert!(cp_files.iter().any(|f| f.path == PATCH_FILE));

        // Control-plane: initConfiguration.patches.directory should be set.
        let cp_init_patches = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .init_configuration
            .as_ref()
            .expect("init configuration should be set")
            .patches
            .as_ref()
            .expect("init configuration patches should be set");

        assert_eq!(cp_init_patches.directory.as_deref(), Some(PATCHES_DIR));

        // Control-plane: joinConfiguration.patches.directory should be set.
        let cp_join_patches = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .join_configuration
            .as_ref()
            .expect("join configuration should be set")
            .patches
            .as_ref()
            .expect("join configuration patches should be set");

        assert_eq!(cp_join_patches.directory.as_deref(), Some(PATCHES_DIR));

        // Worker: kubelet config patch file should be injected.
        let worker_files = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .as_ref()
            .expect("kubeadm config template spec should be set")
            .files
            .as_ref()
            .expect("worker files should be set");

        assert!(worker_files.iter().any(|f| f.path == PATCH_FILE));

        // Worker: joinConfiguration.patches.directory should be set.
        let worker_join_patches = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .as_ref()
            .expect("kubeadm config template spec should be set")
            .join_configuration
            .as_ref()
            .expect("worker join configuration should be set")
            .patches
            .as_ref()
            .expect("worker join configuration patches should be set");

        assert_eq!(worker_join_patches.directory.as_deref(), Some(PATCHES_DIR));
    }

    #[test]
    fn test_patches_when_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_kubelet_serving_tls = false;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let api_server = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .as_ref()
            .and_then(|c| c.api_server.as_ref());

        assert!(
            api_server
                .and_then(|a| a.extra_args.as_ref())
                .and_then(|m| m.get("kubelet-certificate-authority"))
                != Some(&"/etc/kubernetes/pki/ca.crt".to_string())
        );
    }

    #[test]
    fn test_variables() {
        let feature = Feature {};
        let variables = feature.variables();

        assert_eq!(variables.len(), 1);
        assert_eq!(variables[0].name, "enableKubeletServingTLS");
        // Optional so pre-existing clusters without this variable continue to reconcile.
        assert_eq!(variables[0].required, false);
    }
}
