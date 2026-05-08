use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches, ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
            ClusterClassVariablesSchema,
        },
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
use json_patch::{jsonptr::PointerBuf, AddOperation, PatchOperation};
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Debug, Serialize, Deserialize)]
struct Kustomize {
    resources: Vec<String>,
    patches: Vec<KustomizePatch>,
}

#[derive(Debug, Serialize, Deserialize)]
struct KustomizePatchTarget {
    group: String,
    version: String,
    kind: String,
    name: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct KustomizePatch {
    target: KustomizePatchTarget,
    patch: String,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "enableKeystoneAuth")]
    pub enable_keystone_auth: bool,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "keystoneAuth".into(),
            enabled_if: Some("{{ if .enableKeystoneAuth }}true{{end}}".into()),
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
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                        value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                            path: "/etc/kubernetes/keystone-kustomization/kustomization.yml".into(),
                            permissions: Some("0644".into()),
                            owner: Some("root:root".into()),
                            content: Some(serde_yaml::to_string(&Kustomize {
                                resources: vec!["kube-apiserver.yaml".into()],
                                patches: vec![
                                    KustomizePatch {
                                        target: KustomizePatchTarget {
                                            group: "".into(),
                                            version: "v1".into(),
                                            kind: "Pod".into(),
                                            name: "kube-apiserver".into(),
                                        },
                                        patch: serde_yaml::to_string(&vec![
                                            PatchOperation::Add(AddOperation {
                                                path: PointerBuf::parse("/spec/containers/0/command/-").unwrap(),
                                                value: "--authentication-token-webhook-config-file=/etc/kubernetes/webhooks/webhookconfig.yaml".into(),
                                            }),
                                            PatchOperation::Add(AddOperation {
                                                path: PointerBuf::parse("/spec/containers/0/command/-").unwrap(),
                                                value: "--authorization-webhook-config-file=/etc/kubernetes/webhooks/webhookconfig.yaml".into(),
                                            }),
                                            // Append --authorization-mode with Node,RBAC,Webhook
                                            // (NOT just Webhook).  kube-apiserver flag parsing is
                                            // last-occurrence-wins, so this overrides the
                                            // kubeadm default (--authorization-mode=Node,RBAC) but
                                            // keeps Node and RBAC as fallback authorizers.  This
                                            // matters when the keystone-auth webhook backend Pod is
                                            // not yet Running (e.g. during cluster bring-up before
                                            // the management-cluster Helm release is reconciled):
                                            // with plain "Webhook", every API call — including the
                                            // ones the webhook backend itself needs to come up —
                                            // is rejected with "webhook unavailable: 5xx" and the
                                            // cluster locks itself out for several minutes.  With
                                            // Node,RBAC,Webhook, kubelet/system requests still
                                            // authorize via Node + RBAC and the webhook only
                                            // affects Keystone-token-bearing requests.
                                            PatchOperation::Add(AddOperation {
                                                path: PointerBuf::parse("/spec/containers/0/command/-").unwrap(),
                                                value: "--authorization-mode=Node,RBAC,Webhook".into(),
                                            }),
                                        ]).unwrap(),
                                    },
                                ]
                            }).unwrap()),
                            ..Default::default()
                        })),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/preKubeadmCommands/-".into(),
                        value: Some("mkdir -p /etc/kubernetes/keystone-kustomization".into()),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        value: Some("test -f /etc/kubernetes/keystone-kustomization/kube-apiserver.yaml || cp /etc/kubernetes/manifests/kube-apiserver.yaml /etc/kubernetes/keystone-kustomization/kube-apiserver.yaml".into()),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        // NOTE: filter out the kubeadm-default `--authorization-mode=Node,RBAC`
                        // line so the kustomized manifest only carries the appended
                        // `--authorization-mode=Node,RBAC,Webhook`. pflag StringSliceVar
                        // *appends* repeated flags, so a duplicate would yield
                        // `Node,RBAC,Node,RBAC,Webhook` and apiserver bails with
                        // "authorization-mode ... has mode specified more than once".
                        value: Some("kubectl kustomize /etc/kubernetes/keystone-kustomization | sed '/^[[:space:]]*- --authorization-mode=Node,RBAC$/d' > /etc/kubernetes/manifests/kube-apiserver.yaml".into()),
                        ..Default::default()
                    },
                    // Wait for kube-apiserver to come back up after the static-pod manifest
                    // rewrite above.  kubelet detects the manifest change and restarts the
                    // apiserver with the new flags (~5s); subsequent postKubeadmCommands often
                    // query the apiserver and would fail without this barrier.  Bounded loop
                    // with `|| true` so a permanently-broken webhook does not block bootstrap —
                    // with Node,RBAC,Webhook fallback the cluster is still usable.
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        value: Some("for i in $(seq 1 60); do curl -ksf https://127.0.0.1:6443/healthz >/dev/null && break; sleep 5; done || true".into()),
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
    use crate::features::test::{ApplyPatch, TestClusterResources};
    use crate::resources::fixtures::default_values;
    use k8s_openapi::api::core::v1::Pod;
    use pretty_assertions::assert_eq;
    use std::fs::File;

    #[test]
    fn test_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_keystone_auth = false;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("files should be set");

        assert_eq!(
            files
                .iter()
                .find(|f| f.path == "/etc/kubernetes/keystone-kustomization/kustomization.yml"),
            None
        );
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_keystone_auth = true;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("files should be set");

        let file = files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/keystone-kustomization/kustomization.yml")
            .expect("file should be set");

        assert_eq!(
            file.path,
            "/etc/kubernetes/keystone-kustomization/kustomization.yml"
        );
        assert_eq!(file.permissions.as_deref(), Some("0644"));
        assert_eq!(file.owner.as_deref(), Some("root:root"));
        assert!(file.content.is_some());

        let path = format!(
            "{}/tests/fixtures/kube-apiserver.yaml",
            env!("CARGO_MANIFEST_DIR")
        );
        let fd = File::open(&path).expect("file should be set");
        let mut pod: Pod = serde_yaml::from_reader(fd).expect("pod should be set");
        let kustomize: Kustomize =
            serde_yaml::from_str(file.content.as_ref().unwrap()).expect("kustomize should be set");
        let patch = serde_yaml::from_str(&kustomize.patches[0].patch).expect("patch should be set");
        pod.apply_patch(&patch);

        let args = pod.spec.expect("pod to have spec").containers[0]
            .command
            .clone()
            .expect("command should be set");
        assert!(args.contains(&"--authentication-token-webhook-config-file=/etc/kubernetes/webhooks/webhookconfig.yaml".to_string()));
        assert!(args.contains(
            &"--authorization-webhook-config-file=/etc/kubernetes/webhooks/webhookconfig.yaml"
                .to_string()
        ));
        assert!(args.contains(&"--authorization-mode=Node,RBAC,Webhook".to_string()));

        let pre_cmds = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .pre_kubeadm_commands
            .expect("pre commands should be set");
        assert!(pre_cmds.contains(&"mkdir -p /etc/kubernetes/keystone-kustomization".to_string()));

        let post_cmds = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .post_kubeadm_commands
            .expect("post commands should be set");
        assert!(post_cmds.contains(&"test -f /etc/kubernetes/keystone-kustomization/kube-apiserver.yaml || cp /etc/kubernetes/manifests/kube-apiserver.yaml /etc/kubernetes/keystone-kustomization/kube-apiserver.yaml".to_string()));
        assert!(post_cmds.contains(&"kubectl kustomize /etc/kubernetes/keystone-kustomization | sed '/^[[:space:]]*- --authorization-mode=Node,RBAC$/d' > /etc/kubernetes/manifests/kube-apiserver.yaml".to_string()));
        assert!(post_cmds.iter().any(|c| c.contains("https://127.0.0.1:6443/healthz")));
    }
}
