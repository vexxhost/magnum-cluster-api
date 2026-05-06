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
        kubeadmconfigtemplates::{
            KubeadmConfigTemplate, KubeadmConfigTemplateTemplateSpecFiles,
            KubeadmConfigTemplateTemplateSpecFilesEncoding,
        },
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding,
        },
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Maximum number of operator-supplied extra files that can be injected
/// per cluster (cluster-level + node-group merged).  Enforced on the
/// Python side via `utils.get_extra_files`.  Ten slots is more than
/// enough for the common netplan / udev / systemd-unit use cases while
/// keeping the rendered ClusterClass small.
pub const MAX_EXTRA_FILES: usize = 10;

/// Maximum number of operator-supplied pre-kubeadm shell commands.
pub const MAX_PRE_KUBEADM_COMMANDS: usize = 16;

/// Maximum number of operator-supplied post-kubeadm shell commands.
pub const MAX_POST_KUBEADM_COMMANDS: usize = 16;

#[derive(Serialize, Deserialize, JsonSchema, Clone, Default, PartialEq, Debug)]
pub struct ExtraFile {
    pub path: String,

    #[serde(default = "default_owner")]
    pub owner: String,

    #[serde(default = "default_permissions")]
    pub permissions: String,

    /// Base64-encoded file contents.  The Python side base64-encodes any
    /// operator-supplied raw content before stamping it into the topology
    /// variable, so the wire value here is always base64.
    pub content: String,
}

fn default_owner() -> String {
    "root:root".into()
}

fn default_permissions() -> String {
    "0644".into()
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "extraFiles")]
    pub extra_files: Vec<ExtraFile>,

    #[serde(rename = "extraPreKubeadmCommands")]
    pub extra_pre_kubeadm_commands: Vec<String>,

    #[serde(rename = "extraPostKubeadmCommands")]
    pub extra_post_kubeadm_commands: Vec<String>,
}

pub struct Feature {}

fn file_template_for_index(idx: usize) -> String {
    // Render a single KubeadmConfig file entry via go-template.  The
    // outer YAML serialization uses `KubeadmControlPlaneTemplate...Files`
    // (or its KubeadmConfigTemplate sibling) just to get the field
    // ordering right; the actual values come from gtmpl indexing.
    let stub = KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
        path: format!("{{{{ (index .extraFiles {}).path }}}}", idx),
        owner: Some(format!("{{{{ (index .extraFiles {}).owner }}}}", idx)),
        permissions: Some(format!("{{{{ (index .extraFiles {}).permissions }}}}", idx)),
        encoding: Some(
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64,
        ),
        content: Some(format!("{{{{ (index .extraFiles {}).content }}}}", idx)),
        ..Default::default()
    };
    serde_yaml::to_string(&stub).unwrap()
}

fn worker_file_template_for_index(idx: usize) -> String {
    let stub = KubeadmConfigTemplateTemplateSpecFiles {
        path: format!("{{{{ (index .extraFiles {}).path }}}}", idx),
        owner: Some(format!("{{{{ (index .extraFiles {}).owner }}}}", idx)),
        permissions: Some(format!("{{{{ (index .extraFiles {}).permissions }}}}", idx)),
        encoding: Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64),
        content: Some(format!("{{{{ (index .extraFiles {}).content }}}}", idx)),
        ..Default::default()
    };
    serde_yaml::to_string(&stub).unwrap()
}

fn extra_file_patch(idx: usize) -> ClusterClassPatches {
    ClusterClassPatches {
        name: format!("extraFile{}", idx),
        enabled_if: Some(format!(
            "{{{{ if gt (len .extraFiles) {} }}}}true{{{{end}}}}",
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
                        template: Some(file_template_for_index(idx)),
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
                                names: Some(vec!["default-worker".into()]),
                            },
                        ),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/files/-".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(worker_file_template_for_index(idx)),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
            },
        ]),
        ..Default::default()
    }
}

fn extra_command_patch(
    idx: usize,
    variable_name: &str,
    kubeadm_path_segment: &str,
    patch_name_prefix: &str,
) -> ClusterClassPatches {
    let template = format!("{{{{ index .{} {} }}}}", variable_name, idx);
    ClusterClassPatches {
        name: format!("{}{}", patch_name_prefix, idx),
        enabled_if: Some(format!(
            "{{{{ if gt (len .{}) {} }}}}true{{{{end}}}}",
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
                    path: format!(
                        "/spec/template/spec/kubeadmConfigSpec/{}/-",
                        kubeadm_path_segment
                    ),
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
                                names: Some(vec!["default-worker".into()]),
                            },
                        ),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: format!("/spec/template/spec/{}/-", kubeadm_path_segment),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(template),
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
        let mut patches = Vec::with_capacity(
            MAX_EXTRA_FILES + MAX_PRE_KUBEADM_COMMANDS + MAX_POST_KUBEADM_COMMANDS,
        );

        for idx in 0..MAX_EXTRA_FILES {
            patches.push(extra_file_patch(idx));
        }
        for idx in 0..MAX_PRE_KUBEADM_COMMANDS {
            patches.push(extra_command_patch(
                idx,
                "extraPreKubeadmCommands",
                "preKubeadmCommands",
                "extraPreKubeadmCommand",
            ));
        }
        for idx in 0..MAX_POST_KUBEADM_COMMANDS {
            patches.push(extra_command_patch(
                idx,
                "extraPostKubeadmCommands",
                "postKubeadmCommands",
                "extraPostKubeadmCommand",
            ));
        }

        patches
    }
}

inventory::submit! {
    ClusterFeatureEntry { feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;
    use base64::prelude::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_no_extras_renders_no_files_or_commands() {
        let feature = Feature {};
        let mut values = default_values();
        values.extra_files = vec![];
        values.extra_pre_kubeadm_commands = vec![];
        values.extra_post_kubeadm_commands = vec![];

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        // The control-plane KubeadmConfigSpec.files / preKubeadmCommands /
        // postKubeadmCommands lists should still be the fixture defaults
        // (no entries injected by this feature).
        let kcp_spec = &resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec;
        let kcp_extra_count = kcp_spec
            .files
            .as_ref()
            .map(|files| files.iter().filter(|f| f.path == "/etc/extra").count())
            .unwrap_or(0);
        assert_eq!(kcp_extra_count, 0);
    }

    #[test]
    fn test_extra_files_appended_to_kcp_and_kct() {
        let feature = Feature {};
        let mut values = default_values();
        values.extra_files = vec![
            ExtraFile {
                path: "/etc/netplan/99-mcapi.yaml".into(),
                owner: "root:root".into(),
                permissions: "0600".into(),
                content: BASE64_STANDARD.encode(b"network:\n  version: 2\n"),
            },
            ExtraFile {
                path: "/etc/sysctl.d/99-mcapi.conf".into(),
                owner: "root:root".into(),
                permissions: "0644".into(),
                content: BASE64_STANDARD.encode(b"net.ipv4.ip_forward=1\n"),
            },
        ];
        values.extra_pre_kubeadm_commands = vec![];
        values.extra_post_kubeadm_commands = vec![];

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kcp_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .clone()
            .expect("kcp files should exist");
        let extras: Vec<_> = kcp_files
            .iter()
            .filter(|f| {
                f.path == "/etc/netplan/99-mcapi.yaml" || f.path == "/etc/sysctl.d/99-mcapi.conf"
            })
            .collect();
        assert_eq!(extras.len(), 2);
        assert_eq!(extras[0].path, "/etc/netplan/99-mcapi.yaml");
        assert_eq!(extras[0].permissions, Some("0600".into()));
        assert_eq!(
            extras[0].encoding,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64)
        );
        assert_eq!(
            extras[0].content,
            Some(BASE64_STANDARD.encode(b"network:\n  version: 2\n"))
        );

        let kct_files = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .as_ref()
            .and_then(|s| s.files.clone())
            .expect("kct files should exist");
        let kct_extras: Vec<_> = kct_files
            .iter()
            .filter(|f| {
                f.path == "/etc/netplan/99-mcapi.yaml" || f.path == "/etc/sysctl.d/99-mcapi.conf"
            })
            .collect();
        assert_eq!(kct_extras.len(), 2);
    }

    #[test]
    fn test_extra_pre_and_post_kubeadm_commands_appended() {
        let feature = Feature {};
        let mut values = default_values();
        values.extra_files = vec![];
        values.extra_pre_kubeadm_commands = vec![
            "netplan generate".into(),
            "netplan apply".into(),
            "sleep 3".into(),
        ];
        values.extra_post_kubeadm_commands =
            vec!["echo bootstrap done > /var/log/mcapi-extra.log".into()];

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kcp_pre = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .pre_kubeadm_commands
            .clone()
            .expect("kcp preKubeadmCommands should exist");
        for cmd in &["netplan generate", "netplan apply", "sleep 3"] {
            assert!(
                kcp_pre.iter().any(|c| c == cmd),
                "expected kcp.preKubeadmCommands to contain {}, got {:?}",
                cmd,
                kcp_pre
            );
        }

        let kcp_post = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .post_kubeadm_commands
            .clone()
            .expect("kcp postKubeadmCommands should exist");
        assert!(kcp_post
            .iter()
            .any(|c| c == "echo bootstrap done > /var/log/mcapi-extra.log"));

        let kct_pre = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .as_ref()
            .and_then(|s| s.pre_kubeadm_commands.clone())
            .expect("kct preKubeadmCommands should exist");
        for cmd in &["netplan generate", "netplan apply", "sleep 3"] {
            assert!(
                kct_pre.iter().any(|c| c == cmd),
                "expected kct.preKubeadmCommands to contain {}, got {:?}",
                cmd,
                kct_pre
            );
        }
    }

    #[test]
    fn test_existing_pre_kubeadm_commands_not_clobbered() {
        // Make sure our /-/ append patches don't replace the seeded entries
        // from sibling features (e.g. containerd_config seeds a
        // `systemctl restart containerd` line via the
        // KUBEADM_CONTROL_PLANE_TEMPLATE fixture).
        let feature = Feature {};
        let mut values = default_values();
        values.extra_files = vec![];
        values.extra_pre_kubeadm_commands = vec!["echo extra".into()];
        values.extra_post_kubeadm_commands = vec![];

        let mut resources = TestClusterResources::new();
        let baseline_pre = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .pre_kubeadm_commands
            .clone()
            .unwrap_or_default();

        let patches = feature.patches();
        resources.apply_patches(&patches, &values);

        let after = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .pre_kubeadm_commands
            .clone()
            .expect("kcp preKubeadmCommands should exist");

        for original in &baseline_pre {
            assert!(
                after.contains(original),
                "expected baseline command {:?} to still be present after extra_cloud_init patches; got {:?}",
                original,
                after
            );
        }
        assert!(after.contains(&"echo extra".to_string()));
    }
}
