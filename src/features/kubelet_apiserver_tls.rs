// Enable TLS between kubelet and kube-apiserver (kubelet serving cert + client cert to API server).
// See: https://github.com/vexxhost/magnum-cluster-api/issues/365

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
use serde_json::json;

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "enableKubeletApiserverTLS")]
    pub enable_kubelet_apiserver_tls: bool,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "kubeletApiserverTLS".into(),
            enabled_if: Some("{{ if .enableKubeletApiserverTLS }}true{{end}}".into()),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
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
                    // Enable kubelet TLS bootstrap (request cert from API server).
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        value: Some("sed -i '/^cgroupDriver: systemd.*/a serverTLSBootstrap: true' /var/lib/kubelet/config.yaml".into()),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        value: Some("systemctl restart kubelet".into()),
                        ..Default::default()
                    },
                    // Approve pending kubelet CSRs so they get signed.
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        value: Some("kubectl --kubeconfig=/etc/kubernetes/admin.conf certificate approve $(kubectl --kubeconfig=/etc/kubernetes/admin.conf get csr --no-headers 2>/dev/null | awk '{ print $1 }' | tr '\\n' ' ') 2>/dev/null || true".into()),
                        ..Default::default()
                    },
                ],
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

        let post_cmds = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .post_kubeadm_commands
            .as_ref()
            .expect("post kubeadm commands should be set");

        assert!(post_cmds.iter().any(|c| c.contains("serverTLSBootstrap")));
        assert!(post_cmds.iter().any(|c| c == "systemctl restart kubelet"));
        assert!(post_cmds.iter().any(|c| c.contains("certificate approve")));
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
