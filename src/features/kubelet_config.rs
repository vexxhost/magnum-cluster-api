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
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::json;
use typed_builder::TypedBuilder;

#[derive(Clone, Serialize, Deserialize, JsonSchema, TypedBuilder)]
pub struct KubeletConfig {
    pub enabled: bool,

    #[serde(
        default,
        skip_serializing_if = "str::is_empty",
        rename = "cpuManagerPolicy"
    )]
    #[builder(default)]
    pub cpu_manager_policy: String,

    #[serde(
        default,
        skip_serializing_if = "str::is_empty",
        rename = "topologyManagerPolicy"
    )]
    #[builder(default)]
    pub topology_manager_policy: String,

    #[serde(
        default,
        skip_serializing_if = "str::is_empty",
        rename = "reservedSystemCPUs"
    )]
    #[builder(default)]
    pub reserved_system_cpus: String,

    #[serde(default, skip_serializing_if = "is_zero", rename = "maxPods")]
    #[builder(default)]
    pub max_pods: i32,
}

fn is_zero(value: &i32) -> bool {
    *value == 0
}

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "kubeletConfig")]
    pub kubelet_config: KubeletConfig,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        let patch_file = indoc! {r#"
            path: /etc/kubernetes/patches/kubeletconfiguration+merge.yaml
            permissions: "0644"
            owner: root:root
            content: |
              apiVersion: kubelet.config.k8s.io/v1beta1
              kind: KubeletConfiguration
              {{ if .kubeletConfig.cpuManagerPolicy }}cpuManagerPolicy: {{ .kubeletConfig.cpuManagerPolicy }}
              {{ end }}{{ if .kubeletConfig.topologyManagerPolicy }}topologyManagerPolicy: {{ .kubeletConfig.topologyManagerPolicy }}
              {{ end }}{{ if .kubeletConfig.reservedSystemCPUs }}reservedSystemCPUs: {{ .kubeletConfig.reservedSystemCPUs }}
              {{ end }}{{ if .kubeletConfig.maxPods }}maxPods: {{ .kubeletConfig.maxPods }}
              {{ end }}
        "#};

        vec![ClusterClassPatches {
            name: "kubeletConfig".into(),
            enabled_if: Some("{{ if .kubeletConfig.enabled }}true{{end}}".into()),
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
        }]
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
    }

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};
        let mut values = default_values();
        values.kubelet_config = KubeletConfig::builder()
            .enabled(true)
            .cpu_manager_policy("static".into())
            .topology_manager_policy("single-numa-node".into())
            .reserved_system_cpus("0-1".into())
            .max_pods(250)
            .build();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kubeadm_config_spec = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec;
        let control_plane_file = kubeadm_config_spec
            .files
            .expect("control plane files should be set")
            .into_iter()
            .find(|f| f.path == "/etc/kubernetes/patches/kubeletconfiguration+merge.yaml")
            .expect("kubelet config patch should be written");
        let control_plane_content = control_plane_file.content.expect("content should be set");

        assert!(control_plane_content.contains("kind: KubeletConfiguration"));
        assert!(control_plane_content.contains("cpuManagerPolicy: static"));
        assert!(control_plane_content.contains("topologyManagerPolicy: single-numa-node"));
        assert!(control_plane_content.contains("reservedSystemCPUs: 0-1"));
        assert!(control_plane_content.contains("maxPods: 250"));
        assert_eq!(
            kubeadm_config_spec
                .init_configuration
                .expect("init configuration should be set")
                .patches
                .expect("init patches should be set")
                .directory,
            Some("/etc/kubernetes/patches".into())
        );
        assert_eq!(
            kubeadm_config_spec
                .join_configuration
                .expect("join configuration should be set")
                .patches
                .expect("join patches should be set")
                .directory,
            Some("/etc/kubernetes/patches".into())
        );

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("worker spec should be set");
        let worker_file = worker_spec
            .files
            .expect("worker files should be set")
            .into_iter()
            .find(|f| f.path == "/etc/kubernetes/patches/kubeletconfiguration+merge.yaml")
            .expect("worker kubelet config patch should be written");

        assert_eq!(worker_file.content, Some(control_plane_content));
        assert_eq!(
            worker_spec
                .join_configuration
                .expect("worker join configuration should be set")
                .patches
                .expect("worker join patches should be set")
                .directory,
            Some("/etc/kubernetes/patches".into())
        );
    }
}
