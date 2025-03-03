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
            KubeadmConfigTemplateTemplateSpecFormat,
        },
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFormat,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecIgnition,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecIgnitionContainerLinuxConfig,
        },
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use ignition_config::v3_5::{Config, Dropin, Systemd, Unit};
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum OperatingSystem {
    Ubuntu,
    Flatcar,
    RockyLinux,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "operatingSystem")]
    pub operating_system: OperatingSystem,

    #[serde(rename = "aptProxyConfig")]
    pub apt_proxy_config: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "ubuntu".into(),
                enabled_if: Some(r#"{{ if eq .operatingSystem "ubuntu" }}true{{end}}"#.into()),
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
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                            path: "/etc/apt/apt.conf.d/90proxy".to_string(),
                                            owner: Some("root:root".into()),
                                            permissions: Some("0644".to_string()),
                                            encoding: Some(
                                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64,
                                            ),
                                            content: Some("{{ .aptProxyConfig }}".to_string()),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
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
                                machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                    names: Some(vec!["default-worker".to_string()])
                                }),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/files/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmConfigTemplateTemplateSpecFiles {
                                            path: "/etc/apt/apt.conf.d/90proxy".to_string(),
                                            owner: Some("root:root".into()),
                                            permissions: Some("0644".to_string()),
                                            encoding: Some(
                                                KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64,
                                            ),
                                            content: Some("{{ .aptProxyConfig }}".to_string()),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                        ],
                    },
                ]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "flatcar".into(),
                enabled_if: Some(r#"{{ if eq .operatingSystem "flatcar" }}true{{end}}"#.into()),
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
                                path: "/spec/template/spec/kubeadmConfigSpec/preKubeadmCommands/-".into(),
                                value: Some(indoc!(r#"
                                bash -c "sed -i 's/__REPLACE_NODE_NAME__/$(hostname -s)/g' /etc/kubeadm.yml"
                                bash -c "test -f /tmp/containerd-bootstrap || (touch /tmp/containerd-bootstrap && systemctl daemon-reload && systemctl restart containerd)"
                                "#).into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "replace".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/format".into(),
                                value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFormat::Ignition)),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/ignition".into(),
                                value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecIgnition {
                                    container_linux_config: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecIgnitionContainerLinuxConfig {
                                        additional_config: Some(serde_yaml::to_string(&Config {
                                            systemd: Some(Systemd {
                                                units: Some(vec![
                                                    Unit {
                                                        name: "coreos-metadata-sshkeys@.service".into(),
                                                        enabled: Some(true),
                                                        dropins: None,
                                                        contents: None,
                                                        mask: None,
                                                    },
                                                    Unit {
                                                        name: "kubeadm.service".into(),
                                                        enabled: Some(true),
                                                        dropins: Some(vec![
                                                            Dropin {
                                                                name: "10-flatcar.conf".into(),
                                                                contents: Some(
                                                                    indoc!(r#"
                                                                    [Unit]
                                                                    Requires=containerd.service coreos-metadata.service
                                                                    After=containerd.service coreos-metadata.service
                                                                    [Service]
                                                                    EnvironmentFile=/run/metadata/flatcar
                                                                    "#).into(),
                                                                ),
                                                            },
                                                        ]),
                                                        contents: None,
                                                        mask: None,
                                                    }
                                                ]),
                                            }),
                                            ..Default::default()
                                        }).unwrap()),
                                        ..Default::default()
                                    }),
                                })),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "replace".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/initConfiguration/nodeRegistration/name".into(),
                                value: Some("__REPLACE_NODE_NAME__".into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "replace".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/nodeRegistration/name".into(),
                                value: Some("__REPLACE_NODE_NAME__".into()),
                                ..Default::default()
                            },
                        ],
                    },
                    ClusterClassPatchesDefinitions {
                        selector: ClusterClassPatchesDefinitionsSelector {
                            api_version: KubeadmConfigTemplate::api_resource().api_version,
                            kind: KubeadmConfigTemplate::api_resource().kind,
                            match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                                machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                    names: Some(vec!["default-worker".to_string()])
                                }),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/preKubeadmCommands".into(),
                                value: Some(vec![
                                    indoc!(r#"
                                        bash -c "sed -i 's/__REPLACE_NODE_NAME__/$(hostname -s)/g' /etc/kubeadm.yml"
                                        bash -c "test -f /tmp/containerd-bootstrap || (touch /tmp/containerd-bootstrap && systemctl daemon-reload && systemctl restart containerd)"
                                    "#)
                                ].into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/format".into(),
                                value: Some(json!(KubeadmConfigTemplateTemplateSpecFormat::Ignition)),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/ignition".into(),
                                value: Some(json!(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecIgnition {
                                    container_linux_config: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecIgnitionContainerLinuxConfig {
                                        additional_config: Some(serde_yaml::to_string(&Config {
                                            systemd: Some(Systemd {
                                                units: Some(vec![
                                                    Unit {
                                                        name: "coreos-metadata-sshkeys@.service".into(),
                                                        enabled: Some(true),
                                                        dropins: None,
                                                        contents: None,
                                                        mask: None,
                                                    },
                                                    Unit {
                                                        name: "kubeadm.service".into(),
                                                        enabled: Some(true),
                                                        dropins: Some(vec![
                                                            Dropin {
                                                                name: "10-flatcar.conf".into(),
                                                                contents: Some(
                                                                    indoc!(r#"
                                                                    [Unit]
                                                                    Requires=containerd.service coreos-metadata.service
                                                                    After=containerd.service coreos-metadata.service
                                                                    [Service]
                                                                    EnvironmentFile=/run/metadata/flatcar
                                                                    "#).into(),
                                                                ),
                                                            },
                                                        ]),
                                                        contents: None,
                                                        mask: None,
                                                    }
                                                ]),
                                            }),
                                            ..Default::default()
                                        }).unwrap()),
                                        ..Default::default()
                                    }),
                                })),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "replace".into(),
                                path: "/spec/template/spec/joinConfiguration/nodeRegistration/name".into(),
                                value: Some("__REPLACE_NODE_NAME__".into()),
                                ..Default::default()
                            },
                        ],
                    },
                ]),
                ..Default::default()
            }
        ]
    }
}

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::resources::fixtures::default_values;
    use crate::features::test::TestClusterResources;
    use base64::prelude::*;
    use indoc::indoc;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_apply_patches_for_ubuntu() {
        let feature = Feature {};

        let mut values = default_values();
        values.operating_system = OperatingSystem::Ubuntu;
        values.apt_proxy_config = BASE64_STANDARD.encode(indoc!(
            "
            Acquire::http::Proxy \"http://proxy.example.com\";
            Acquire::https::Proxy \"http://proxy.example.com\";
            "
        ));

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kcpt_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .expect("files should be set");

        let kcpt_proxy_file = kcpt_files
            .iter()
            .find(|f| f.path == "/etc/apt/apt.conf.d/90proxy")
            .expect("file should be set");
        assert_eq!(kcpt_proxy_file.path, "/etc/apt/apt.conf.d/90proxy");
        assert_eq!(kcpt_proxy_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kcpt_proxy_file.permissions.as_deref(), Some("0644"));
        assert_eq!(
            kcpt_proxy_file.encoding,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kcpt_proxy_file.content,
            Some(values.apt_proxy_config.clone())
        );

        let kct_files = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("spec should be set")
            .files
            .expect("files should be set");

        let kct_proxy_file = kct_files
            .iter()
            .find(|f| f.path == "/etc/apt/apt.conf.d/90proxy")
            .expect("file should be set");
        assert_eq!(kct_proxy_file.path, "/etc/apt/apt.conf.d/90proxy");
        assert_eq!(kct_proxy_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kct_proxy_file.permissions.as_deref(), Some("0644"));
        assert_eq!(
            kct_proxy_file.encoding,
            Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kct_proxy_file.content,
            Some(values.apt_proxy_config.clone())
        );
    }

    #[test]
    fn test_apply_patches_for_flatcar() {
        let feature = Feature {};

        let mut values = default_values();
        values.operating_system = OperatingSystem::Flatcar;
        values.apt_proxy_config = BASE64_STANDARD.encode("");

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .pre_kubeadm_commands,
            Some(vec![
                "rm /var/lib/etcd/lost+found -rf".to_string(),
                "bash /run/kubeadm/configure-kube-proxy.sh".to_string(),
                indoc!(r#"
                bash -c "sed -i 's/__REPLACE_NODE_NAME__/$(hostname -s)/g' /etc/kubeadm.yml"
                bash -c "test -f /tmp/containerd-bootstrap || (touch /tmp/containerd-bootstrap && systemctl daemon-reload && systemctl restart containerd)"
                "#)
                .into()
            ])
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .format,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFormat::Ignition)
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .ignition
                .expect("ignition should be set")
                .container_linux_config
                .expect("container linux config should be set")
                .additional_config
                .expect("additional config should be set"),
            serde_yaml::to_string(&Config {
                systemd: Some(Systemd {
                    units: Some(vec![
                        Unit {
                            name: "coreos-metadata-sshkeys@.service".into(),
                            enabled: Some(true),
                            dropins: None,
                            contents: None,
                            mask: None,
                        },
                        Unit {
                            name: "kubeadm.service".into(),
                            enabled: Some(true),
                            dropins: Some(vec![Dropin {
                                name: "10-flatcar.conf".into(),
                                contents: Some(
                                    indoc!(
                                        r#"
                                    [Unit]
                                    Requires=containerd.service coreos-metadata.service
                                    After=containerd.service coreos-metadata.service
                                    [Service]
                                    EnvironmentFile=/run/metadata/flatcar
                                    "#
                                    )
                                    .into(),
                                ),
                            },]),
                            contents: None,
                            mask: None,
                        }
                    ]),
                }),
                ..Default::default()
            })
            .unwrap()
        );

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
                .name,
            Some("__REPLACE_NODE_NAME__".into())
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .join_configuration
                .expect("join configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .name,
            Some("__REPLACE_NODE_NAME__".into())
        );

        assert_eq!(
            resources
                .kubeadm_config_template
                .clone()
                .spec
                .template
                .spec
                .expect("spec should be set")
                .pre_kubeadm_commands,
            Some(vec![
                indoc!(r#"
                    bash -c "sed -i 's/__REPLACE_NODE_NAME__/$(hostname -s)/g' /etc/kubeadm.yml"
                    bash -c "test -f /tmp/containerd-bootstrap || (touch /tmp/containerd-bootstrap && systemctl daemon-reload && systemctl restart containerd)"
                "#)
                .into()
            ])
        );

        assert_eq!(
            resources
                .kubeadm_config_template
                .clone()
                .spec
                .template
                .spec
                .expect("spec should be set")
                .format,
            Some(KubeadmConfigTemplateTemplateSpecFormat::Ignition)
        );

        assert_eq!(
            resources
                .kubeadm_config_template
                .clone()
                .spec
                .template
                .spec
                .expect("spec should be set")
                .ignition
                .expect("ignition should be set")
                .container_linux_config
                .expect("container linux config should be set")
                .additional_config
                .expect("additional config should be set"),
            serde_yaml::to_string(&Config {
                systemd: Some(Systemd {
                    units: Some(vec![
                        Unit {
                            name: "coreos-metadata-sshkeys@.service".into(),
                            enabled: Some(true),
                            dropins: None,
                            contents: None,
                            mask: None,
                        },
                        Unit {
                            name: "kubeadm.service".into(),
                            enabled: Some(true),
                            dropins: Some(vec![Dropin {
                                name: "10-flatcar.conf".into(),
                                contents: Some(
                                    indoc!(
                                        r#"
                                        [Unit]
                                        Requires=containerd.service coreos-metadata.service
                                        After=containerd.service coreos-metadata.service
                                        [Service]
                                        EnvironmentFile=/run/metadata/flatcar
                                        "#
                                    )
                                    .into(),
                                ),
                            },]),
                            contents: None,
                            mask: None,
                        }
                    ]),
                }),
                ..Default::default()
            })
            .unwrap()
        );

        assert_eq!(
            resources
                .kubeadm_config_template
                .clone()
                .spec
                .template
                .spec
                .expect("spec should be set")
                .join_configuration
                .expect("join configuration should be set")
                .node_registration
                .expect("node registration should be set")
                .name,
            Some("__REPLACE_NODE_NAME__".into())
        );
    }
}
