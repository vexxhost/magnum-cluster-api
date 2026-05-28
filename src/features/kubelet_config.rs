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
        containerd_config::WORKER_PRE_KUBEADM_COMMANDS, ClusterClassVariablesSchemaExt,
        ClusterFeatureEntry, ClusterFeaturePatches, ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::json;
use typed_builder::TypedBuilder;

pub const MAX_CONFIG_PROFILE_FILES: usize = 10;
pub const MAX_CONFIG_PROFILE_PRE_COMMANDS: usize = 16;
pub const MAX_CONFIG_PROFILE_POST_COMMANDS: usize = 16;

#[derive(Clone, Default, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct KubeletConfig {
    #[serde(default)]
    #[builder(default)]
    pub enabled: bool,

    #[serde(default, skip_serializing_if = "str::is_empty", rename = "configYaml")]
    #[builder(default)]
    pub config_yaml: String,
}

#[derive(Clone, Default, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct ConfigProfile {
    #[serde(default)]
    #[builder(default)]
    pub enabled: bool,

    #[serde(default)]
    #[serde(rename = "kubeletConfig")]
    #[builder(default)]
    pub kubelet_config: KubeletConfig,

    #[serde(default)]
    #[serde(rename = "filesYaml")]
    #[builder(default)]
    pub files_yaml: Vec<String>,

    #[serde(default)]
    #[serde(rename = "preKubeadmCommands")]
    #[builder(default)]
    pub pre_kubeadm_commands: Vec<String>,

    #[serde(default)]
    #[serde(rename = "postKubeadmCommands")]
    #[builder(default)]
    pub post_kubeadm_commands: Vec<String>,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "configProfile")]
    pub config_profile: ConfigProfile,
}

pub struct Feature {}

fn profile_file_patch(idx: usize) -> ClusterClassPatches {
    ClusterClassPatches {
        name: format!("configProfileFile{}", idx),
        enabled_if: Some(format!(
            "{{{{ if gt (len .configProfile.filesYaml) {} }}}}true{{{{end}}}}",
            idx
        )),
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
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(format!("{{{{ index .configProfile.filesYaml {} }}}}", idx)),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
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
                    path: "/spec/template/spec/files/-".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(format!("{{{{ index .configProfile.filesYaml {} }}}}", idx)),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
            },
        ]),
        ..Default::default()
    }
}

fn profile_command_patch(
    idx: usize,
    variable_name: &str,
    kubeadm_path_segment: &str,
    patch_name_prefix: &str,
) -> ClusterClassPatches {
    let template = format!("{{{{ index .configProfile.{} {} }}}}", variable_name, idx);
    let control_plane_path = format!(
        "/spec/template/spec/kubeadmConfigSpec/{}/-",
        kubeadm_path_segment
    );
    let (worker_path, worker_template) = if idx == 0 {
        let mut commands = Vec::new();

        if kubeadm_path_segment == "preKubeadmCommands" {
            commands.extend(
                WORKER_PRE_KUBEADM_COMMANDS
                    .iter()
                    .map(|command| format!("- {}", command)),
            );
        }

        commands.push(format!(
            "- {{{{ index .configProfile.{} 0 }}}}",
            variable_name
        ));

        (
            format!("/spec/template/spec/{}", kubeadm_path_segment),
            commands.join("\n"),
        )
    } else {
        (
            format!("/spec/template/spec/{}/-", kubeadm_path_segment),
            template.clone(),
        )
    };
    ClusterClassPatches {
        name: format!("{}{}", patch_name_prefix, idx),
        enabled_if: Some(format!(
            "{{{{ if gt (len .configProfile.{}) {} }}}}true{{{{end}}}}",
            variable_name, idx
        )),
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
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: control_plane_path,
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(template.clone()),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
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
                    path: worker_path,
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(worker_template),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
            },
        ]),
        ..Default::default()
    }
}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        let patch_file = indoc! {r#"
            path: /etc/kubernetes/patches/kubeletconfiguration+merge.yaml
            permissions: "0644"
            owner: root:root
            content: |
              apiVersion: kubelet.config.k8s.io/v1beta1
              kind: KubeletConfiguration
              {{ .configProfile.kubeletConfig.configYaml }}
        "#};

        let mut patches = vec![ClusterClassPatches {
            name: "configProfileKubeletConfig".into(),
            enabled_if: Some("{{ if .configProfile.kubeletConfig.enabled }}true{{end}}".into()),
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
                            path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(patch_file.into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/initConfiguration/patches"
                                .into(),
                            value: Some(json!({
                                "directory": "/etc/kubernetes/patches"
                            })),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/patches"
                                .into(),
                            value: Some(json!({
                                "directory": "/etc/kubernetes/patches"
                            })),
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
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/files/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(patch_file.into()),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/joinConfiguration/patches".into(),
                            value: Some(json!({
                                "directory": "/etc/kubernetes/patches"
                            })),
                            ..Default::default()
                        },
                    ],
                },
            ]),
            ..Default::default()
        }];

        for idx in 0..MAX_CONFIG_PROFILE_FILES {
            patches.push(profile_file_patch(idx));
        }
        for idx in 0..MAX_CONFIG_PROFILE_PRE_COMMANDS {
            patches.push(profile_command_patch(
                idx,
                "preKubeadmCommands",
                "preKubeadmCommands",
                "configProfilePreKubeadmCommand",
            ));
        }
        for idx in 0..MAX_CONFIG_PROFILE_POST_COMMANDS {
            patches.push(profile_command_patch(
                idx,
                "postKubeadmCommands",
                "postKubeadmCommands",
                "configProfilePostKubeadmCommand",
            ));
        }

        patches
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
    use serde_json::json;

    #[test]
    fn test_disabled() {
        let feature = Feature {};
        let values = default_values();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let control_plane_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("control plane files should be set");
        assert_eq!(
            control_plane_files
                .iter()
                .find(|f| f.path == "/etc/kubernetes/patches/kubeletconfiguration+merge.yaml"),
            None
        );

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        assert_eq!(worker_spec.pre_kubeadm_commands, Some(vec![]));
        assert_eq!(worker_spec.post_kubeadm_commands, Some(vec![]));
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};
        let mut values = default_values();
        values.config_profile = ConfigProfile::builder()
            .enabled(true)
            .kubelet_config(
                KubeletConfig::builder()
                    .enabled(true)
                    .config_yaml(
                        indoc! {r#"
                            cpuManagerPolicy: static
                              reservedSystemCPUs: 0-1
                              maxPods: 250
                        "#}
                        .trim()
                        .into(),
                    )
                    .build(),
            )
            .files_yaml(vec![indoc! {r#"
                path: /etc/gpu-init.sh
                permissions: "0755"
                owner: root:root
                content: ZWNobyBncHU=
                encoding: base64
            "#}
            .trim()
            .into()])
            .pre_kubeadm_commands(vec!["bash /etc/gpu-init.sh".into()])
            .post_kubeadm_commands(vec!["echo done > /etc/gpu-init.done".into()])
            .build();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        {
            let worker_spec = resources
                .kubeadm_config_template
                .spec
                .template
                .spec
                .as_mut()
                .expect("worker spec should be set");
            worker_spec.pre_kubeadm_commands = None;
            worker_spec.post_kubeadm_commands = None;
        }
        resources.apply_patches(&patches, &values);

        let kubeadm_config_spec = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec;
        let control_plane_files = kubeadm_config_spec
            .files
            .expect("control plane files should be set");
        let kubelet_file = control_plane_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/patches/kubeletconfiguration+merge.yaml")
            .expect("kubelet config patch should be written");
        let kubelet_content = kubelet_file
            .content
            .as_ref()
            .expect("content should be set");

        assert!(kubelet_content.contains("kind: KubeletConfiguration"));
        assert!(kubelet_content.contains("cpuManagerPolicy: static"));
        assert!(kubelet_content.contains("reservedSystemCPUs: 0-1"));
        assert!(kubelet_content.contains("maxPods: 250"));
        assert!(control_plane_files
            .iter()
            .any(|f| f.path == "/etc/gpu-init.sh"));
        let pre_commands = kubeadm_config_spec
            .pre_kubeadm_commands
            .expect("pre commands should be set");
        assert!(pre_commands.contains(&"rm /var/lib/etcd/lost+found -rf".to_string()));
        assert!(pre_commands.contains(&"bash /run/kubeadm/configure-kube-proxy.sh".to_string()));
        assert!(pre_commands.contains(&"bash /etc/gpu-init.sh".to_string()));
        let post_commands = kubeadm_config_spec
            .post_kubeadm_commands
            .expect("post commands should be set");
        assert!(post_commands.contains(&"echo PLACEHOLDER".to_string()));
        assert!(post_commands.contains(&"echo done > /etc/gpu-init.done".to_string()));
        assert_eq!(
            kubeadm_config_spec
                .init_configuration
                .expect("init configuration should be set")
                .patches
                .expect("init patches should be set")
                .directory,
            Some("/etc/kubernetes/patches".into())
        );

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        assert!(worker_spec
            .files
            .expect("worker files should be set")
            .iter()
            .any(|f| f.path == "/etc/gpu-init.sh"));
        assert_eq!(
            worker_spec
                .pre_kubeadm_commands
                .expect("worker pre commands should be set"),
            vec![
                "systemctl daemon-reload".to_string(),
                "systemctl restart containerd".to_string(),
                "bash /etc/gpu-init.sh".to_string()
            ]
        );
        assert_eq!(
            worker_spec
                .post_kubeadm_commands
                .expect("worker post commands should be set"),
            vec!["echo done > /etc/gpu-init.done".to_string()]
        );
    }

    fn resources_with_config_profile(profile: ConfigProfile) -> TestClusterResources {
        let feature = Feature {};
        let mut values = default_values();
        values.config_profile = profile;

        let mut resources = TestClusterResources::new();
        {
            let worker_spec = resources
                .kubeadm_config_template
                .spec
                .template
                .spec
                .as_mut()
                .expect("worker spec should be set");
            worker_spec.pre_kubeadm_commands = None;
            worker_spec.post_kubeadm_commands = None;
        }
        resources.apply_patches(&feature.patches(), &values);
        resources
    }

    #[test]
    fn test_config_profile_deserializes_solo_keys() {
        let cases = vec![
            json!({
                "enabled": true,
                "kubeletConfig": {
                    "enabled": true,
                    "configYaml": "maxPods: 250",
                },
            }),
            json!({
                "enabled": true,
                "filesYaml": [
                    "path: /etc/profile-file\ncontent: cHJvZmlsZQo=\nencoding: base64",
                ],
            }),
            json!({
                "enabled": true,
                "preKubeadmCommands": ["echo pre"],
            }),
            json!({
                "enabled": true,
                "postKubeadmCommands": ["echo post"],
            }),
        ];

        for case in cases {
            let profile: ConfigProfile =
                serde_json::from_value(case).expect("profile should deserialize");
            assert!(profile.enabled);
        }
    }

    #[test]
    fn test_apply_patches_with_solo_kubelet_config() {
        let resources = resources_with_config_profile(
            ConfigProfile::builder()
                .enabled(true)
                .kubelet_config(
                    KubeletConfig::builder()
                        .enabled(true)
                        .config_yaml("maxPods: 250".into())
                        .build(),
                )
                .build(),
        );

        let control_plane_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("control plane files should be set");
        assert!(control_plane_files
            .iter()
            .any(|f| f.path == "/etc/kubernetes/patches/kubeletconfiguration+merge.yaml"));
    }

    #[test]
    fn test_apply_patches_with_solo_file() {
        let resources = resources_with_config_profile(
            ConfigProfile::builder()
                .enabled(true)
                .files_yaml(vec![
                    "path: /etc/profile-file\ncontent: cHJvZmlsZQo=\nencoding: base64".into(),
                ])
                .build(),
        );

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        assert!(worker_spec
            .files
            .expect("worker files should be set")
            .iter()
            .any(|f| f.path == "/etc/profile-file"));
    }

    #[test]
    fn test_apply_patches_with_solo_pre_kubeadm_command() {
        let resources = resources_with_config_profile(
            ConfigProfile::builder()
                .enabled(true)
                .pre_kubeadm_commands(vec!["echo pre".into()])
                .build(),
        );

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        assert_eq!(
            worker_spec
                .pre_kubeadm_commands
                .expect("worker pre commands should be set"),
            vec![
                "systemctl daemon-reload".to_string(),
                "systemctl restart containerd".to_string(),
                "echo pre".to_string()
            ]
        );
    }

    #[test]
    fn test_worker_pre_kubeadm_commands_preserve_containerd_commands() {
        let containerd_feature = crate::features::containerd_config::Feature {};
        let feature = Feature {};
        let mut values = default_values();
        values.config_profile = ConfigProfile::builder()
            .enabled(true)
            .pre_kubeadm_commands(vec!["echo pre".into(), "echo second".into()])
            .build();

        let mut patches = containerd_feature.patches();
        patches.extend(feature.patches());

        let mut resources = TestClusterResources::new();
        {
            let worker_spec = resources
                .kubeadm_config_template
                .spec
                .template
                .spec
                .as_mut()
                .expect("worker spec should be set");
            worker_spec.pre_kubeadm_commands = None;
        }
        resources.apply_patches(&patches, &values);

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        assert_eq!(
            worker_spec
                .pre_kubeadm_commands
                .expect("worker pre commands should be set"),
            vec![
                "systemctl daemon-reload".to_string(),
                "systemctl restart containerd".to_string(),
                "echo pre".to_string(),
                "echo second".to_string()
            ]
        );
    }

    #[test]
    fn test_apply_patches_with_solo_post_kubeadm_command() {
        let resources = resources_with_config_profile(
            ConfigProfile::builder()
                .enabled(true)
                .post_kubeadm_commands(vec!["echo post".into()])
                .build(),
        );

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        assert_eq!(
            worker_spec
                .post_kubeadm_commands
                .expect("worker post commands should be set"),
            vec!["echo post".to_string()]
        );
    }
}
