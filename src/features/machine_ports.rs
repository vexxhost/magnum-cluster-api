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
    features::{ClusterFeatureEntry, ClusterFeaturePatches, ClusterFeatureVariables},
};
use kube::CustomResourceExt;
use serde_json::json;

pub struct Feature {}

fn machine_ports_variable(name: &str) -> ClusterClassVariables {
    let schema = ClusterClassVariablesSchema {
        open_apiv3_schema: serde_json::from_value(json!({
            "type": "array",
            "default": [],
            "items": {
                "type": "object",
                "required": ["nameSuffix", "network"],
                "properties": {
                    "nameSuffix": {"type": "string"},
                    "network": {
                        "type": "object",
                        "required": ["id"],
                        "properties": {
                            "id": {"type": "string"}
                        }
                    },
                    "fixedIPs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["subnet"],
                            "properties": {
                                "subnet": {
                                    "type": "object",
                                    "required": ["id"],
                                    "properties": {
                                        "id": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "disablePortSecurity": {"type": "boolean"},
                    "vnicType": {"type": "string"}
                }
            }
        }))
        .expect("machine port ClusterClass schema must be valid"),
    };
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
    use serde::{Deserialize, Serialize};
    use serde_json::Value;

    #[derive(Clone, Deserialize, Serialize)]
    struct MachinePortNetwork {
        id: String,
    }

    #[derive(Clone, Deserialize, Serialize)]
    struct MachinePortSubnet {
        id: String,
    }

    #[derive(Clone, Deserialize, Serialize)]
    struct MachinePortFixedIp {
        subnet: MachinePortSubnet,
    }

    #[derive(Clone, Deserialize, Serialize)]
    struct MachinePort {
        #[serde(rename = "nameSuffix")]
        name_suffix: String,
        network: MachinePortNetwork,
        #[serde(default, skip_serializing_if = "Option::is_none", rename = "fixedIPs")]
        fixed_ips: Option<Vec<MachinePortFixedIp>>,
        #[serde(
            default,
            skip_serializing_if = "Option::is_none",
            rename = "disablePortSecurity"
        )]
        disable_port_security: Option<bool>,
        #[serde(default, skip_serializing_if = "Option::is_none", rename = "vnicType")]
        vnic_type: Option<String>,
    }

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

            let schema = serde_json::to_value(&variable.schema.open_apiv3_schema).unwrap();
            assert_scalar_schema_types(&schema, "openAPIV3Schema");

            let item = schema.get("items").expect("machine port item schema");
            let properties = item
                .get("properties")
                .and_then(Value::as_object)
                .expect("machine port properties");
            for optional in ["fixedIPs", "disablePortSecurity", "vnicType"] {
                assert!(
                    !item
                        .get("required")
                        .and_then(Value::as_array)
                        .is_some_and(|required| { required.iter().any(|entry| entry == optional) }),
                    "{optional} must remain optional"
                );
                assert!(properties.contains_key(optional));
            }
        }
    }

    fn assert_scalar_schema_types(value: &Value, path: &str) {
        match value {
            Value::Object(object) => {
                if let Some(schema_type) = object.get("type") {
                    assert!(
                        schema_type.is_string(),
                        "{path}.type must be a scalar string, got {schema_type}"
                    );
                }
                for (key, child) in object {
                    assert_scalar_schema_types(child, &format!("{path}.{key}"));
                }
            }
            Value::Array(array) => {
                for (index, child) in array.iter().enumerate() {
                    assert_scalar_schema_types(child, &format!("{path}[{index}]"));
                }
            }
            _ => {}
        }
    }
}
