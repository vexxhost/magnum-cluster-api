use super::ClusterFeature;
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
    ClusterClassVariablesSchema, ClusterClassVariablesSchemaOpenApiv3Schema,
};
use maplit::btreemap;
use serde_json::json;

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        // TODO: refactor these two to somewhere generic
        let bool_schema = ClusterClassVariablesSchemaOpenApiv3Schema {
            r#type: Some("boolean".into()),
            ..Default::default()
        };
        let string_schema = ClusterClassVariablesSchemaOpenApiv3Schema {
            r#type: Some("string".into()),
            ..Default::default()
        };

        vec![ClusterClassVariables {
            name: "auditLog".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema {
                open_apiv3_schema: ClusterClassVariablesSchemaOpenApiv3Schema {
                    r#type: Some("object".into()),
                    required: Some(vec![
                        "enabled".into(),
                        "maxAge".into(),
                        "maxBackup".into(),
                        "maxSize".into(),
                    ]),
                    properties: Some(json!(btreemap! {
                        "enabled".to_string() => bool_schema.clone(),
                        "maxAge".to_string() => string_schema.clone(),
                        "maxBackup".to_string() => string_schema.clone(),
                        "maxSize".to_string() => string_schema.clone(),
                    })),
                    ..Default::default()
                },
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
                            // TODO: detect this from the kubeadmcontrolplanetemplates module
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
                                        serde_yaml::to_string(&btreemap! {
                                            "name" => "audit-policy",
                                            "hostPath" => "/etc/kubernetes/audit-policy",
                                            "mountPath" => "/etc/kubernetes/audit-policy",
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
                                        serde_yaml::to_string(&btreemap! {
                                            "name" => "audit-logs",
                                            "hostPath" => "/var/log/kubernetes/audit",
                                            "mountPath" => "/var/log/audit",
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
        cluster_api::kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate, KubeadmControlPlaneTemplateSpec,
            KubeadmControlPlaneTemplateTemplate, KubeadmControlPlaneTemplateTemplateSpec,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
        },
        features::test::{
            assert_subset_of_btreemap, ApplyPatch, ClusterClassPatchEnabled, ToPatch,
        },
    };
    use maplit::hashmap;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_disabled() {
        let feature = Feature {};
        let values = hashmap! {
            "auditLog".to_string() => hashmap! {
                "enabled".to_string() => false,
            }
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
            "auditLog".to_string() => hashmap! {
                "enabled".to_string() => true,
            }
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
            "auditLog".to_string() => hashmap! {
                "enabled".into() => "true".to_string(),
                "maxAge".into() => "30".to_string(),
                "maxBackup".into() => "10".to_string(),
                "maxSize".into() => "100".to_string(),
            }
        };

        let patches = feature.patches();
        let patch = patches.get(0).expect("patch should be set");
        let is_enabled = patch.is_enabled(values.clone());

        assert_eq!(is_enabled, true);

        // TODO: move this out since this is generic/standard
        let mut kcpt = KubeadmControlPlaneTemplate {
            metadata: Default::default(),
            spec: KubeadmControlPlaneTemplateSpec {
                template: KubeadmControlPlaneTemplateTemplate {
                    spec: KubeadmControlPlaneTemplateTemplateSpec {
                        kubeadm_config_spec: KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec {
                            cluster_configuration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration {
                                api_server: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer {
                                    extra_args: Some({
                                        btreemap! {
                                            "cloud-provider".to_string() => "external".to_string(),
                                            "profiling".to_string() => "false".to_string(),
                                        }
                                    }),
                                    // Note(oleks): Add this as default as a workaround of the json patch limitation # noqa: E501
                                    // https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass#json-patches-tips--tricks
                                    extra_volumes: Some(vec![
                                        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                            name: "webhooks".to_string(),
                                            host_path: "/etc/kubernetes/webhooks".to_string(),
                                            mount_path: "/etc/kubernetes/webhooks".to_string(),
                                            ..Default::default()
                                        }
                                    ]),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }),
                            ..Default::default()
                        },
                        ..Default::default()
                    },
                    ..Default::default()
                },
                ..Default::default()
            }
        };

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
                "audit-log-maxage".to_string() => values["auditLog"]["maxAge"].to_string(),
                "audit-log-maxbackup".to_string() => values["auditLog"]["maxBackup"].to_string(),
                "audit-log-maxsize".to_string() => values["auditLog"]["maxSize"].to_string(),
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
