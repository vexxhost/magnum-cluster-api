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
                                            PatchOperation::Add(AddOperation {
                                                path: PointerBuf::parse("/spec/containers/0/command/-").unwrap(),
                                                value: "--authorization-mode=Webhook".into(),
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
                        value: Some("cp /etc/kubernetes/manifests/kube-apiserver.yaml /etc/kubernetes/keystone-kustomization/kube-apiserver.yaml".into()),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/postKubeadmCommands/-".into(),
                        value: Some("kubectl kustomize /etc/kubernetes/keystone-kustomization -o /etc/kubernetes/manifests/kube-apiserver.yaml".into()),
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
        assert!(args.contains(&"--authorization-mode=Webhook".to_string()));

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
        assert!(post_cmds.contains(&"cp /etc/kubernetes/manifests/kube-apiserver.yaml /etc/kubernetes/keystone-kustomization/kube-apiserver.yaml".to_string()));
        assert!(post_cmds.contains(&"kubectl kustomize /etc/kubernetes/keystone-kustomization -o /etc/kubernetes/manifests/kube-apiserver.yaml".to_string()));
    }
}
