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
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecInitConfigurationPatches,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecJoinConfigurationPatches,
        },
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use json_patch::{
    jsonptr::PointerBuf, AddOperation, PatchOperation, ReplaceOperation, TestOperation,
};
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};
use serde_json::json;

// Share kubeadm's single patch directory with kubelet serving verification.
const KUBEADM_PATCHES_DIRECTORY: &str = "/etc/kubernetes/patches";
const KUBE_APISERVER_PATCH_FILE: &str = "/etc/kubernetes/patches/kube-apiserver0+json.yaml";
const AUTHORIZATION_CONFIG_FILE: &str = "/etc/kubernetes/webhooks/authorization-config.yaml";
const AUTHORIZATION_CONFIG: &str =
    include_str!("../../data/keystone-auth/authorization-config.yaml");

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
                            path: KUBE_APISERVER_PATCH_FILE.into(),
                            permissions: Some("0644".into()),
                            owner: Some("root:root".into()),
                            content: Some(serde_yaml::to_string(&vec![
                                PatchOperation::Add(AddOperation {
                                    path: PointerBuf::parse("/spec/containers/0/command/-").unwrap(),
                                    value: "--authentication-token-webhook-config-file=/etc/kubernetes/webhooks/webhookconfig.yaml".into(),
                                }),
                                // kubeadm needs a Forbidden response to bootstrap admin RBAC.
                                // The structured configuration skips the Keystone webhook for
                                // native Kubernetes identities while retaining Node and RBAC.
                                PatchOperation::Test(TestOperation {
                                    path: PointerBuf::parse("/spec/containers/0/command/3").unwrap(),
                                    value: "--authorization-mode=Node,RBAC".into(),
                                }),
                                PatchOperation::Replace(ReplaceOperation {
                                    path: PointerBuf::parse("/spec/containers/0/command/3").unwrap(),
                                    value: format!("--authorization-config={AUTHORIZATION_CONFIG_FILE}").into(),
                                }),
                            ]).unwrap()),
                            ..Default::default()
                        })),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                        value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                            path: AUTHORIZATION_CONFIG_FILE.into(),
                            permissions: Some("0644".into()),
                            owner: Some("root:root".into()),
                            content: Some(AUTHORIZATION_CONFIG.into()),
                            ..Default::default()
                        })),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/initConfiguration/patches".into(),
                        value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecInitConfigurationPatches {
                            directory: Some(KUBEADM_PATCHES_DIRECTORY.into()),
                        })),
                        ..Default::default()
                    },
                    ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/patches".into(),
                        value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecJoinConfigurationPatches {
                            directory: Some(KUBEADM_PATCHES_DIRECTORY.into()),
                        })),
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
    fn test_keystone_and_kubelet_patches_share_directory_in_either_order() {
        use crate::features::kubelet_serving_certificate_verification;

        let mut values = default_values();
        values.enable_keystone_auth = true;
        values.enable_kubelet_serving_certificate_verification = true;

        for keystone_first in [true, false] {
            let mut resources = TestClusterResources::new();
            let keystone = Feature {}.patches();
            let kubelet = kubelet_serving_certificate_verification::Feature {}.patches();
            let patches = if keystone_first {
                [keystone, kubelet].concat()
            } else {
                [kubelet, keystone].concat()
            };
            resources.apply_patches(&patches, &values);

            let config = resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec;
            let init_directory = config
                .init_configuration
                .unwrap()
                .patches
                .unwrap()
                .directory
                .unwrap();
            let join_directory = config
                .join_configuration
                .unwrap()
                .patches
                .unwrap()
                .directory
                .unwrap();
            assert_eq!(init_directory, join_directory);

            let files = config.files.unwrap();
            for filename in [
                "kube-apiserver0+json.yaml",
                "kubeletconfiguration0+strategic.json",
            ] {
                assert!(
                    files
                        .iter()
                        .any(|file| file.path == format!("{init_directory}/{filename}")),
                    "kubeadm cannot discover {filename} in {init_directory}"
                );
            }
        }
    }

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
            files.iter().find(|f| f.path == KUBE_APISERVER_PATCH_FILE),
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
            .find(|f| f.path == KUBE_APISERVER_PATCH_FILE)
            .expect("file should be set");

        assert_eq!(file.path, KUBE_APISERVER_PATCH_FILE);
        assert_eq!(file.permissions.as_deref(), Some("0644"));
        assert_eq!(file.owner.as_deref(), Some("root:root"));
        assert!(file.content.is_some());

        let path = format!(
            "{}/tests/fixtures/kube-apiserver.yaml",
            env!("CARGO_MANIFEST_DIR")
        );
        let fd = File::open(&path).expect("file should be set");
        let mut pod: Pod = serde_yaml::from_reader(fd).expect("pod should be set");
        let patch: json_patch::Patch =
            serde_yaml::from_str(file.content.as_ref().unwrap()).expect("patch should be set");
        assert_eq!(
            patch.0.get(1),
            Some(&PatchOperation::Test(TestOperation {
                path: PointerBuf::parse("/spec/containers/0/command/3").unwrap(),
                value: "--authorization-mode=Node,RBAC".into(),
            }))
        );
        pod.apply_patch(&patch);

        let args = pod.spec.expect("pod to have spec").containers[0]
            .command
            .clone()
            .expect("command should be set");
        assert!(args.contains(&"--authentication-token-webhook-config-file=/etc/kubernetes/webhooks/webhookconfig.yaml".to_string()));
        assert!(args.contains(&format!(
            "--authorization-config={AUTHORIZATION_CONFIG_FILE}"
        )));
        assert!(!args
            .iter()
            .any(|arg| arg.starts_with("--authorization-mode=")));
        assert!(!args
            .iter()
            .any(|arg| arg.starts_with("--authorization-webhook-")));

        let authorization_file = files
            .iter()
            .find(|file| file.path == AUTHORIZATION_CONFIG_FILE)
            .expect("authorization configuration should be written before kubeadm");
        let authorization: serde_json::Value =
            serde_yaml::from_str(authorization_file.content.as_ref().unwrap()).unwrap();
        assert_eq!(authorization["kind"], "AuthorizationConfiguration");
        assert_eq!(authorization["authorizers"][0]["type"], "Node");
        assert_eq!(authorization["authorizers"][1]["type"], "RBAC");
        assert_eq!(authorization["authorizers"][2]["type"], "Webhook");
        assert_eq!(
            authorization["authorizers"][2]["webhook"]["failurePolicy"],
            "NoOpinion"
        );
        assert_eq!(
            authorization["authorizers"][2]["webhook"]["connectionInfo"]["kubeConfigFile"],
            "/etc/kubernetes/webhooks/webhookconfig.yaml"
        );

        let init_patches = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .init_configuration
            .expect("init configuration should be set")
            .patches
            .expect("init patches should be set");
        assert_eq!(
            init_patches.directory.as_deref(),
            Some(KUBEADM_PATCHES_DIRECTORY)
        );

        let join_patches = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .join_configuration
            .expect("join configuration should be set")
            .patches
            .expect("join patches should be set");
        assert_eq!(
            join_patches.directory.as_deref(),
            Some(KUBEADM_PATCHES_DIRECTORY)
        );

        let post_cmds = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .post_kubeadm_commands
            .expect("post commands should be set");
        assert!(!post_cmds.iter().any(|c| c.contains("kubectl kustomize")));
        assert!(!post_cmds
            .iter()
            .any(|c| c.contains("keystone-kustomization")));
    }
}
