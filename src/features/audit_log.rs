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
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
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
use serde_json::json;
use typed_builder::TypedBuilder;

#[derive(Clone, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct AuditLogConfig {
    pub enabled: bool,

    #[serde(rename = "maxAge")]
    pub max_age: String,

    #[serde(rename = "maxBackup")]
    pub max_backup: String,

    #[serde(rename = "maxSize")]
    pub max_size: String,
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "auditLog")]
    pub audit_log: AuditLogConfig,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
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
                                value: Some(json!(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                    name: "audit-policy".to_string(),
                                    host_path: "/etc/kubernetes/audit-policy".to_string(),
                                    mount_path: "/etc/kubernetes/audit-policy".to_string(),
                                    ..Default::default()
                                })),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraVolumes/-".into(),
                                value: Some(json!(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                    name: "audit-logs".to_string(),
                                    host_path: "/var/log/kubernetes/audit".to_string(),
                                    mount_path: "/var/log/audit".to_string(),
                                    ..Default::default()
                                })),
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

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cluster_api::kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
        features::test::TestClusterResources, resources::fixtures::default_values,
    };
    use maplit::btreemap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.audit_log = AuditLogConfig::builder()
            .enabled(false)
            .max_age("30".into())
            .max_backup("10".into())
            .max_size("100".into())
            .build();

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
            .expect("cluster_configuration should be set")
            .api_server
            .expect("api_server should be set");

        assert_eq!(
            &btreemap! {
                "cloud-provider".to_string() => "external".to_string(),
                "profiling".to_string() => "false".to_string(),
            },
            &api_server.extra_args.expect("extra_args should be set"),
        );
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};

        let mut values = default_values();
        values.audit_log = AuditLogConfig::builder()
            .enabled(true)
            .max_age("30".into())
            .max_backup("10".into())
            .max_size("100".into())
            .build();

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
            .expect("cluster_configuration should be set")
            .api_server
            .expect("api_server should be set");

        assert_eq!(
            &btreemap! {
                "audit-log-maxage".to_string() => values.audit_log.max_age.to_string(),
                "audit-log-maxbackup".to_string() => values.audit_log.max_backup.to_string(),
                "audit-log-maxsize".to_string() => values.audit_log.max_size.to_string(),
                "audit-log-path".to_string() => "/var/log/audit/kube-apiserver-audit.log".to_string(),
                "audit-policy-file".to_string() => "/etc/kubernetes/audit-policy/apiserver-audit-policy.yaml".to_string(),
                "cloud-provider".to_string() => "external".to_string(),
                "profiling".to_string() => "false".to_string(),
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
