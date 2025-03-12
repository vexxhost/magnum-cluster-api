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
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "cloudControllerManagerConfig")]
    pub cloud_controller_manager_config: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "cloudControllerManagerConfig".into(),
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
                                        path: "/etc/kubernetes/cloud.conf".to_string(),
                                        owner: Some("root:root".into()),
                                        permissions: Some("0600".to_string()),
                                        encoding: Some(
                                            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64,
                                        ),
                                        content: Some("{{ .cloudControllerManagerConfig }}".to_string()),
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
                                        path: "/etc/kubernetes/cloud.conf".to_string(),
                                        owner: Some("root:root".into()),
                                        permissions: Some("0600".to_string()),
                                        encoding: Some(
                                            KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64,
                                        ),
                                        content: Some("{{ .cloudControllerManagerConfig }}".to_string()),
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
        }]
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
    use pretty_assertions::assert_eq;

    #[test]
    fn test_apply_patches() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let kcpt_spec = resources.kubeadm_control_plane_template.spec.template.spec;

        let kcpt_files = kcpt_spec
            .kubeadm_config_spec
            .files
            .expect("files should be set");

        let kcpt_ccm_file = kcpt_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/cloud.conf")
            .expect("file should be set");
        assert_eq!(kcpt_ccm_file.path, "/etc/kubernetes/cloud.conf");
        assert_eq!(kcpt_ccm_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kcpt_ccm_file.permissions.as_deref(), Some("0600"));
        assert_eq!(
            kcpt_ccm_file.encoding,
            Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kcpt_ccm_file.content,
            Some(values.cloud_controller_manager_config.clone())
        );

        let kct_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("spec should be set");

        let kct_files = kct_spec.files.expect("files should be set");

        let kct_ccm_file = kct_files
            .iter()
            .find(|f| f.path == "/etc/kubernetes/cloud.conf")
            .expect("file should be set");
        assert_eq!(kct_ccm_file.path, "/etc/kubernetes/cloud.conf");
        assert_eq!(kct_ccm_file.owner.as_deref(), Some("root:root"));
        assert_eq!(kct_ccm_file.permissions.as_deref(), Some("0600"));
        assert_eq!(
            kct_ccm_file.encoding,
            Some(KubeadmConfigTemplateTemplateSpecFilesEncoding::Base64)
        );
        assert_eq!(
            kct_ccm_file.content,
            Some(values.cloud_controller_manager_config.clone())
        );
    }
}
