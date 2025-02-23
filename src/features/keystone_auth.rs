use super::ClusterFeature;
use crate::cluster_api::kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles;
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsSelector, ClusterClassPatchesDefinitionsSelectorMatchResources,
    ClusterClassVariables, ClusterClassVariablesSchema, ClusterClassVariablesSchemaOpenApiv3Schema,
};
use json_patch::{AddOperation, PatchOperation};
use jsonptr::PointerBuf;
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

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![ClusterClassVariables {
            name: "enableKeystoneAuth".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema {
                open_apiv3_schema: ClusterClassVariablesSchemaOpenApiv3Schema {
                    r#type: Some("boolean".into()),
                    ..Default::default()
                },
            },
        }]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "keystoneAuth".into(),
            enabled_if: Some("{{ if .enableKeystoneAuth }}true{{end}}".into()),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector {
                    // TODO: point to CRD
                    api_version: "controlplane.cluster.x-k8s.io/v1beta1".into(),
                    kind: "KubeadmControlPlaneTemplate".into(),
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
                                                value: "--authentication-mode=Webhook".into(),
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

#[cfg(test)]
mod tests {
    use std::fs::File;

    use super::*;
    use crate::{
        cluster_api::kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate, KubeadmControlPlaneTemplateSpec,
            KubeadmControlPlaneTemplateTemplate, KubeadmControlPlaneTemplateTemplateSpec,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec,
        },
        features::test::{ApplyPatch, ClusterClassPatchEnabled, ToPatch},
    };
    use k8s_openapi::api::core::v1::Pod;
    use maplit::hashmap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled() {
        let feature = Feature {};
        let values = hashmap! {
            "enableKeystoneAuth".to_string() => false,
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, false);
    }

    #[test]
    fn test_enabled() {
        let feature = Feature {};
        let values = hashmap! {
            "enableKeystoneAuth".to_string() => true,
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, true);
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};
        let values = hashmap! {
            "enableKeystoneAuth".to_string() => "true".to_string(),
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        assert_eq!(patch.is_enabled(values.clone()), true);

        let mut kcpt = KubeadmControlPlaneTemplate {
            metadata: Default::default(),
            spec: KubeadmControlPlaneTemplateSpec {
                template: KubeadmControlPlaneTemplateTemplate {
                    spec: KubeadmControlPlaneTemplateTemplateSpec {
                        kubeadm_config_spec:
                            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec {
                                files: Some(vec![]),
                                pre_kubeadm_commands: Some(vec![]),
                                post_kubeadm_commands: Some(vec![]),
                                ..Default::default()
                            },
                        ..Default::default()
                    },
                    ..Default::default()
                },
                ..Default::default()
            },
        };

        patch
            .definitions
            .as_ref()
            .unwrap()
            .iter()
            .for_each(|definition| {
                let p = definition.json_patches.clone().to_patch(values.clone());
                kcpt.apply_patch(&p);
            });

        let files = kcpt
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
        let patch =
            serde_yaml::from_str(&kustomize.patches[0].patch).expect("patch should be set");
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
        assert!(args.contains(&"--authentication-mode=Webhook".to_string()));

        let pre_cmds = kcpt
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .pre_kubeadm_commands
            .expect("pre commands should be set");
        assert!(pre_cmds.contains(&"mkdir -p /etc/kubernetes/keystone-kustomization".to_string()));

        let post_cmds = kcpt
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
