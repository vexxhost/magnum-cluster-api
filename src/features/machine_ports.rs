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
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Clone, Debug, Deserialize, JsonSchema, PartialEq, Serialize)]
pub struct MachinePortNetwork {
    pub id: String,
}

#[derive(Clone, Debug, Deserialize, JsonSchema, PartialEq, Serialize)]
pub struct MachinePortSubnet {
    pub id: String,
}

#[derive(Clone, Debug, Deserialize, JsonSchema, PartialEq, Serialize)]
pub struct MachinePortFixedIp {
    pub subnet: MachinePortSubnet,
}

#[derive(Clone, Debug, Deserialize, JsonSchema, PartialEq, Serialize)]
pub struct MachinePort {
    #[serde(rename = "nameSuffix")]
    pub name_suffix: String,
    pub network: MachinePortNetwork,
    #[serde(default, skip_serializing_if = "Option::is_none", rename = "fixedIPs")]
    pub fixed_ips: Option<Vec<MachinePortFixedIp>>,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        rename = "disablePortSecurity"
    )]
    pub disable_port_security: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none", rename = "vnicType")]
    pub vnic_type: Option<String>,
}

pub struct Feature {}

fn machine_ports_variable(name: &str) -> ClusterClassVariables {
    let mut schema = ClusterClassVariablesSchema::from_object::<Vec<MachinePort>>();
    schema.open_apiv3_schema.default = Some(json!([]));
    ClusterClassVariables {
        name: name.into(),
        metadata: None,
        required: false,
        schema,
    }
}

impl ClusterFeatureVariables for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            machine_ports_variable("controlPlaneMachinePorts"),
            machine_ports_variable("workerMachinePorts"),
        ]
    }
}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "controlPlaneMachinePorts".into(),
                enabled_if: Some(
                    r#"{{ if .controlPlaneMachinePorts }}true{{end}}"#.into(),
                ),
                definitions: Some(vec![ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: OpenStackMachineTemplate::api_resource().api_version,
                        kind: OpenStackMachineTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            control_plane: Some(true),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                        op: "add".into(),
                        path: "/spec/template/spec/ports".into(),
                        value_from: Some(
                            ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("controlPlaneMachinePorts".into()),
                                ..Default::default()
                            },
                        ),
                        ..Default::default()
                    }],
                }]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "workerMachinePorts".into(),
                enabled_if: Some(r#"{{ if .workerMachinePorts }}true{{end}}"#.into()),
                definitions: Some(vec![ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: OpenStackMachineTemplate::api_resource().api_version,
                        kind: OpenStackMachineTemplate::api_resource().kind,
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
                        path: "/spec/template/spec/ports".into(),
                        value_from: Some(
                            ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                variable: Some("workerMachinePorts".into()),
                                ..Default::default()
                            },
                        ),
                        ..Default::default()
                    }],
                }]),
                ..Default::default()
            },
        ]
    }
}

inventory::submit! {
    ClusterFeatureEntry { feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;

    #[derive(Deserialize, Serialize)]
    struct TestValues {
        #[serde(rename = "controlPlaneMachinePorts")]
        control_plane_machine_ports: Vec<MachinePort>,
        #[serde(rename = "workerMachinePorts")]
        worker_machine_ports: Vec<MachinePort>,
    }

    fn port(role: &str, network: &str) -> MachinePort {
        MachinePort {
            name_suffix: role.into(),
            network: MachinePortNetwork { id: network.into() },
            fixed_ips: None,
            disable_port_security: Some(true),
            vnic_type: Some("normal".into()),
        }
    }

    #[test]
    fn test_empty_defaults_do_not_render_ports() {
        let feature = Feature {};
        let mut resources = TestClusterResources::new();
        resources.apply_patches(
            &feature.patches(),
            &TestValues {
                control_plane_machine_ports: vec![],
                worker_machine_ports: vec![],
            },
        );

        assert!(resources
            .control_plane_openstack_machine_template
            .spec
            .template
            .spec
            .ports
            .is_none());
        assert!(resources
            .worker_openstack_machine_template
            .spec
            .template
            .spec
            .ports
            .is_none());
    }

    #[test]
    fn test_ports_render_for_each_machine_role() {
        let feature = Feature {};
        let control_plane_ports = vec![port("primary", "network-a")];
        let worker_ports = vec![port("primary", "network-a"), port("data", "network-b")];
        let mut resources = TestClusterResources::new();
        resources.apply_patches(
            &feature.patches(),
            &TestValues {
                control_plane_machine_ports: control_plane_ports.clone(),
                worker_machine_ports: worker_ports.clone(),
            },
        );

        let rendered_control_plane = resources
            .control_plane_openstack_machine_template
            .spec
            .template
            .spec
            .ports
            .expect("control-plane ports should be rendered");
        let rendered_workers = resources
            .worker_openstack_machine_template
            .spec
            .template
            .spec
            .ports
            .expect("worker ports should be rendered");
        assert_eq!(
            serde_json::to_value(rendered_control_plane).unwrap(),
            serde_json::to_value(control_plane_ports).unwrap()
        );
        assert_eq!(
            serde_json::to_value(rendered_workers).unwrap(),
            serde_json::to_value(worker_ports).unwrap()
        );
    }

    #[test]
    fn test_variables_are_optional_with_empty_defaults() {
        let feature = Feature {};
        for variable in feature.variables() {
            assert!(!variable.required);
            assert_eq!(variable.schema.open_apiv3_schema.default, Some(json!([])));
        }
    }
}
