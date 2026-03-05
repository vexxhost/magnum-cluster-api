// Enable TLS between kubelet and kube-apiserver (kubelet serving cert + client cert to API server).
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
        kubeadmconfigtemplates::KubeadmConfigTemplate,
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
use serde_json::json;

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "enableKubeletApiserverTLS")]
    pub enable_kubelet_apiserver_tls: bool,
}

pub struct Feature {}

const SERVER_TLS_BOOTSTRAP_CMD: &str = "if ! grep -q '^serverTLSBootstrap:' /var/lib/kubelet/config.yaml; then if grep -q '^cgroupDriver:' /var/lib/kubelet/config.yaml; then sed -i '0,/^cgroupDriver:/s//&\\nserverTLSBootstrap: true/' /var/lib/kubelet/config.yaml; else printf '\\nserverTLSBootstrap: true\\n' >> /var/lib/kubelet/config.yaml; fi; fi";

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "kubeletApiserverTLS".into(),
            enabled_if: Some("{{ if .enableKubeletApiserverTLS }}true{{end}}".into()),
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
                        // API server verifies kubelet client certificates using the cluster CA.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/kubelet-certificate-authority".into(),
                            value: Some(json!("/etc/kubernetes/pki/ca.crt")),
                            ..Default::default()
                        },
                        // Enable kubelet TLS bootstrap (request cert from API server), idempotent.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                            value: Some(SERVER_TLS_BOOTSTRAP_CMD.into()),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                            value: Some("systemctl restart kubelet".into()),
                            ..Default::default()
                        },
                        // Approve pending kubelet-serving CSRs so they get signed, without approving arbitrary CSRs.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                            value: Some(r#"kubectl --kubeconfig=/etc/kubernetes/admin.conf get csr --no-headers 2>/dev/null | awk '$3=="kubernetes.io/kubelet-serving" && $NF!="Approved" { print $1 }' | xargs -r -n1 kubectl --kubeconfig=/etc/kubernetes/admin.conf certificate approve 2>/dev/null || true"#.into()),
                            ..Default::default()
                        },
                    ],
                },
                // Worker nodes also need serverTLSBootstrap to request serving certs from the API.
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
                        // Enable kubelet TLS bootstrap on worker nodes, idempotent.
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/postKubeadmCommands/-".into(),
                            value: Some(SERVER_TLS_BOOTSTRAP_CMD.into()),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/postKubeadmCommands/-".into(),
                            value: Some("systemctl restart kubelet".into()),
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
        values.enable_kubelet_apiserver_tls = true;

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

        let cp_post_cmds = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .post_kubeadm_commands
            .as_ref()
            .expect("control plane post kubeadm commands should be set");

        assert!(cp_post_cmds.iter().any(|c| c.contains("serverTLSBootstrap")));
        assert!(cp_post_cmds.iter().any(|c| c == "systemctl restart kubelet"));
        assert!(cp_post_cmds.iter().any(|c| c.contains("certificate approve")));
        assert!(cp_post_cmds.iter().any(|c| c.contains("kubernetes.io/kubelet-serving")));

        let worker_post_cmds = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .as_ref()
            .expect("kubeadm config template spec should be set")
            .post_kubeadm_commands
            .as_ref()
            .expect("worker post kubeadm commands should be set");

        assert!(worker_post_cmds.iter().any(|c| c.contains("serverTLSBootstrap")));
        assert!(worker_post_cmds.iter().any(|c| c == "systemctl restart kubelet"));
        // CSR approval should NOT be in worker commands (admin.conf not available on workers)
        assert!(!worker_post_cmds.iter().any(|c| c.contains("certificate approve")));
    }

    #[test]
    fn test_patches_when_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_kubelet_apiserver_tls = false;

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
        assert_eq!(variables[0].name, "enableKubeletApiserverTLS");
        assert_eq!(variables[0].required, true);
    }
}
