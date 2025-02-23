use super::ClusterFeature;
use crate::{
    cluster_api::kubeadmcontrolplanetemplates::{
        KubeadmControlPlaneTemplate,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
    },
    features::ClusterClassVariablesSchemaOpenApiv3SchemaExt,
};
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
    ClusterClassVariablesSchema, ClusterClassVariablesSchemaOpenApiv3Schema,
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
pub struct Config {
    pub enabled: bool,

    #[serde(rename = "maxAge")]
    pub max_age: String,

    #[serde(rename = "maxBackup")]
    pub max_backup: String,

    #[serde(rename = "maxSize")]
    pub max_size: String,
}

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![ClusterClassVariables {
            name: "auditLog".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema {
                open_apiv3_schema: ClusterClassVariablesSchemaOpenApiv3Schema::from_object::<Config>(
                ),
            },
        }]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "auditLog".into(),
                enabled_if: Some("{{ if .auditLog.enabled }}true{{end}}".into()),
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
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-path".into(),
                                value: Some("/var/log/audit/kube-apiserver-audit.log".into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-maxage".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("auditLog.maxAge".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-maxbackup".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("auditLog.maxBackup".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-maxsize".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    variable: Some("auditLog.maxSize".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-policy-file".into(),
                                value: Some("/etc/kubernetes/audit-policy/apiserver-audit-policy.yaml".into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraVolumes/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                            name: "audit-policy".to_string(),
                                            host_path: "/etc/kubernetes/audit-policy".to_string(),
                                            mount_path: "/etc/kubernetes/audit-policy".to_string(),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraVolumes/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                            name: "audit-logs".to_string(),
                                            host_path: "/var/log/kubernetes/audit".to_string(),
                                            mount_path: "/var/log/audit".to_string(),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                        ],
                    }

                ]),
                ..Default::default()
            }
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cluster_api::kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
        features::test::{
            assert_subset_of_btreemap, ApplyPatch, ClusterClassPatchEnabled, ToPatch, KCPT_WIP,
        },
    };
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "auditLog")]
        audit_log: Config,
    }

    #[test]
    fn test_disabled() {
        let feature = Feature {};
        let values = Values {
            audit_log: Config {
                enabled: false,
                max_age: "30".to_string(),
                max_backup: "10".to_string(),
                max_size: "100".to_string(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, false);
    }

    #[test]
    fn test_enabled() {
        let feature = Feature {};
        let values = Values {
            audit_log: Config {
                enabled: true,
                max_age: "30".to_string(),
                max_backup: "10".to_string(),
                max_size: "100".to_string(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values);

        assert_eq!(is_enabled, true);
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};
        let values = Values {
            audit_log: Config {
                enabled: true,
                max_age: "30".to_string(),
                max_backup: "10".to_string(),
                max_size: "100".to_string(),
            },
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values.clone());

        assert_eq!(is_enabled, true);

        let mut kcpt = KCPT_WIP.clone();

        // TODO: create a trait that will take kcp, etc and apply the patches
        patch
            .definitions
            .as_ref()
            .expect("definitions should be set")
            .into_iter()
            .for_each(|definition| {
                let p = definition.json_patches.clone().to_patch(values.clone());
                kcpt.apply_patch(&p);
            });

        let api_server = kcpt
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .cluster_configuration
            .expect("cluster_configuration should be set")
            .api_server
            .expect("api_server should be set");

        assert_subset_of_btreemap(
            &btreemap! {
                "audit-log-path".to_string() => "/var/log/audit/kube-apiserver-audit.log".to_string(),
                "audit-log-maxage".to_string() => values.audit_log.max_age.to_string(),
                "audit-log-maxbackup".to_string() => values.audit_log.max_backup.to_string(),
                "audit-log-maxsize".to_string() => values.audit_log.max_size.to_string(),
                "audit-policy-file".to_string() => "/etc/kubernetes/audit-policy/apiserver-audit-policy.yaml".to_string(),
            },
            &api_server.extra_args.expect("extra_args should be set"),
        );

        let extra_volumes = api_server
            .extra_volumes
            .expect("extra_volumes should be set");

        assert!(extra_volumes.contains(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
            name: "audit-policy".to_string(),
            host_path: "/etc/kubernetes/audit-policy".to_string(),
            mount_path: "/etc/kubernetes/audit-policy".to_string(),
            ..Default::default()
        }));
        assert!(extra_volumes.contains(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
            name: "audit-logs".to_string(),
            host_path: "/var/log/kubernetes/audit".to_string(),
            mount_path: "/var/log/audit".to_string(),
            ..Default::default()
        }));
    }
}
