include!(concat!(env!("OUT_DIR"), "/values.rs"));

use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClass, ClusterClassControlPlane, ClusterClassControlPlaneMachineHealthCheck,
            ClusterClassControlPlaneMachineHealthCheckUnhealthyConditions,
            ClusterClassControlPlaneMachineInfrastructure, ClusterClassInfrastructure,
            ClusterClassPatches, ClusterClassSpec, ClusterClassVariables, ClusterClassWorkers,
            ClusterClassWorkersMachineDeployments,
            ClusterClassWorkersMachineDeploymentsMachineHealthCheck,
            ClusterClassWorkersMachineDeploymentsMachineHealthCheckUnhealthyConditions,
            ClusterClassWorkersMachineDeploymentsTemplate,
            ClusterClassWorkersMachineDeploymentsTemplateBootstrap,
            ClusterClassWorkersMachineDeploymentsTemplateInfrastructure,
        },
        kubeadmconfigtemplates::KubeadmConfigTemplate,
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
        openstackclustertemplates::OpenStackClusterTemplate,
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::ClusterFeatureEntry,
};
use k8s_openapi::{api::core::v1::ObjectReference, apimachinery::pkg::util::intstr::IntOrString};
use kube::{api::ObjectMeta, CustomResourceExt};

pub struct ClusterClassBuilder {
    variables: Vec<ClusterClassVariables>,
    patches: Vec<ClusterClassPatches>,
}

impl ClusterClassBuilder {
    pub fn new() -> Self {
        Self {
            variables: Vec::new(),
            patches: Vec::new(),
        }
    }

    pub fn build(self, metadata: ObjectMeta) -> ClusterClass {
        ClusterClass {
            metadata: metadata.clone(),
            spec: ClusterClassSpec {
                control_plane: Some(ClusterClassControlPlane {
                    machine_health_check: Some(ClusterClassControlPlaneMachineHealthCheck {
                        max_unhealthy: Some(IntOrString::String("80%".to_string())),
                        unhealthy_conditions: Some(vec![
                            ClusterClassControlPlaneMachineHealthCheckUnhealthyConditions {
                                r#type: "Ready".to_string(),
                                timeout: "5m0s".to_string(),
                                status: "False".to_string(),
                            },
                            ClusterClassControlPlaneMachineHealthCheckUnhealthyConditions {
                                r#type: "Ready".to_string(),
                                timeout: "5m0s".to_string(),
                                status: "Unknown".to_string(),
                            },
                        ]),
                        ..Default::default()
                    }),
                    machine_infrastructure: Some(ClusterClassControlPlaneMachineInfrastructure {
                        r#ref: ObjectReference {
                            api_version: Some(OpenStackMachineTemplate::api_resource().api_version),
                            kind: Some(OpenStackMachineTemplate::api_resource().kind),
                            name: metadata.name.clone(),
                            namespace: metadata.namespace.clone(),
                            ..Default::default()
                        },
                    }),
                    node_volume_detach_timeout: Some("5m0s".to_string()),
                    r#ref: ObjectReference {
                        api_version: Some(KubeadmControlPlaneTemplate::api_resource().api_version),
                        kind: Some(KubeadmControlPlaneTemplate::api_resource().kind),
                        name: metadata.name.clone(),
                        namespace: metadata.namespace.clone(),
                        ..Default::default()
                    },
                    ..Default::default()
                }),
                infrastructure: Some(ClusterClassInfrastructure {
                    r#ref: ObjectReference {
                        api_version: Some(OpenStackClusterTemplate::api_resource().api_version),
                        kind: Some(OpenStackClusterTemplate::api_resource().kind),
                        name: metadata.name.clone(),
                        namespace: metadata.namespace.clone(),
                        ..Default::default()
                    },
                }),
                patches: Some(self.patches),
                variables: Some(self.variables),
                workers: Some(ClusterClassWorkers {
                    machine_deployments: Some(vec![
                        ClusterClassWorkersMachineDeployments {
                            class: "default-worker".to_string(),
                            machine_health_check: Some(ClusterClassWorkersMachineDeploymentsMachineHealthCheck {
                                max_unhealthy: Some(IntOrString::String("80%".to_string())),
                                unhealthy_conditions: Some(vec![
                                    ClusterClassWorkersMachineDeploymentsMachineHealthCheckUnhealthyConditions {
                                        r#type: "Ready".to_string(),
                                        timeout: "5m0s".to_string(),
                                        status: "False".to_string(),
                                    },
                                    ClusterClassWorkersMachineDeploymentsMachineHealthCheckUnhealthyConditions {
                                        r#type: "Ready".to_string(),
                                        timeout: "5m0s".to_string(),
                                        status: "Unknown".to_string(),
                                    },
                                ]),
                                ..Default::default()
                            }),
                            node_volume_detach_timeout: Some("5m0s".to_string()),
                            template: ClusterClassWorkersMachineDeploymentsTemplate {
                                bootstrap: ClusterClassWorkersMachineDeploymentsTemplateBootstrap {
                                    r#ref: ObjectReference {
                                        api_version: Some(KubeadmConfigTemplate::api_resource().api_version),
                                        kind: Some(KubeadmConfigTemplate::api_resource().kind),
                                        name: metadata.name.clone(),
                                        namespace: metadata.namespace.clone(),
                                        ..Default::default()
                                    },
                                },
                                infrastructure: ClusterClassWorkersMachineDeploymentsTemplateInfrastructure {
                                    r#ref: ObjectReference {
                                        api_version: Some(OpenStackMachineTemplate::api_resource().api_version),
                                        kind: Some(OpenStackMachineTemplate::api_resource().kind),
                                        name: metadata.name.clone(),
                                        namespace: metadata.namespace.clone(),
                                        ..Default::default()
                                    },
                                },
                                ..Default::default()
                            },
                            ..Default::default()
                        }
                    ]),
                    ..Default::default()
                }),
            },
            ..Default::default()
        }
    }

    pub fn default(metadata: ObjectMeta) -> ClusterClass {
        let mut cc = ClusterClassBuilder::new();

        for entry in inventory::iter::<ClusterFeatureEntry> {
            cc.variables.extend(entry.feature.variables());
            cc.patches.extend(entry.feature.patches());
        }

        cc.build(metadata)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_default() {
        let metadata = ObjectMeta {
            name: Some("test".to_string()),
            namespace: Some("default".to_string()),
            ..Default::default()
        };
        let cluster_class = ClusterClassBuilder::default(metadata);

        assert_eq!(cluster_class.metadata.name, Some("test".to_string()));
        assert_eq!(
            cluster_class.metadata.namespace,
            Some("default".to_string())
        );

        assert_eq!(cluster_class.spec.control_plane.is_some(), true);
        assert_eq!(cluster_class.spec.infrastructure.is_some(), true);
        assert_eq!(cluster_class.spec.patches.is_some(), true);
        assert_eq!(cluster_class.spec.variables.is_some(), true);
        assert_eq!(cluster_class.spec.workers.is_some(), true);
    }
}
