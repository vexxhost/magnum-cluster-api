use crate::cluster_api::{clusters::Cluster, machines::Machine};
use std::collections::HashMap;

trait ClusterExt {
    fn is_ready(&self) -> bool;
}

impl ClusterExt for Cluster {
    fn is_ready(&self) -> bool {
        self.status
            .as_ref()
            .and_then(|status| status.conditions.as_ref())
            .and_then(|conditions| {
                conditions
                    .iter()
                    .find(|condition| condition.type_ == "Available")
                    .map(|condition| condition.status == "True")
            })
            .unwrap_or(false)
    }
}

trait MachineExt {
    fn is_ready(&self) -> bool;
}

impl MachineExt for Machine {
    fn is_ready(&self) -> bool {
        self.status
            .as_ref()
            .and_then(|status| status.conditions.as_ref())
            .and_then(|conditions| {
                conditions
                    .iter()
                    .find(|condition| condition.type_ == "NodeHealthy")
                    .map(|condition| condition.status == "True")
            })
            .unwrap_or(false)
    }
}

type MachineHealthStatusReason = HashMap<String, bool>;

trait MachineListExt {
    fn to_health_status_reason(&self) -> MachineHealthStatusReason;
}

impl MachineListExt for [Machine] {
    fn to_health_status_reason(&self) -> MachineHealthStatusReason {
        self.iter()
            .filter_map(|machine| {
                machine
                    .spec
                    .infrastructure_ref
                    .name
                    .as_ref()
                    .map(|name| (format!("{}.Ready", name), machine.is_ready()))
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cluster_api::{
        clusters::ClusterStatus,
        machines::{MachineSpec, MachineStatus},
    };
    use k8s_openapi::{
        api::core::v1::ObjectReference,
        apimachinery::pkg::apis::meta::v1::{Condition, Time},
    };
    use kube::api::ObjectMeta;
    use maplit::hashmap;
    use pretty_assertions::assert_eq;

    fn build_conditions(conditions: HashMap<&str, &str>) -> Option<Vec<Condition>> {
        Some(
            conditions
                .iter()
                .map(|(type_, status)| Condition {
                    type_: type_.to_string(),
                    status: status.to_string(),
                    last_transition_time: Time(k8s_openapi::chrono::Utc::now()),
                    message: "".to_string(),
                    reason: "".to_string(),
                    observed_generation: None,
                })
                .collect::<Vec<_>>(),
        )
        .filter(|vec| !vec.is_empty())
    }

    #[test]
    fn test_cluster_is_ready_when_available_condition_is_true() {
        let cluster = Cluster {
            status: Some(ClusterStatus {
                conditions: build_conditions(hashmap! {
                    "Available" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert!(cluster.is_ready());
    }

    #[test]
    fn test_cluster_is_not_ready_when_available_condition_is_false() {
        let cluster = Cluster {
            status: Some(ClusterStatus {
                conditions: build_conditions(hashmap! {
                    "Available" => "False",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(cluster.is_ready(), false);
    }

    #[test]
    fn test_cluster_is_not_ready_when_available_condition_not_present() {
        let cluster = Cluster {
            status: Some(ClusterStatus {
                conditions: build_conditions(hashmap! {
                    "Ready" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(cluster.is_ready(), false);
    }

    #[test]
    fn test_cluster_is_not_ready_when_conditions_empty() {
        let cluster = Cluster {
            status: Some(ClusterStatus {
                conditions: Some(vec![]),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(cluster.is_ready(), false);
    }

    #[test]
    fn test_cluster_is_not_ready_when_conditions_none() {
        let cluster = Cluster {
            status: Some(ClusterStatus {
                conditions: build_conditions(hashmap! {}),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(cluster.is_ready(), false);
    }

    #[test]
    fn test_cluster_is_not_ready_when_status_none() {
        let cluster = Cluster {
            status: None,
            ..Default::default()
        };

        assert_eq!(cluster.is_ready(), false);
    }

    #[test]
    fn test_multiple_conditions_only_cares_about_available() {
        let cluster = Cluster {
            status: Some(ClusterStatus {
                conditions: build_conditions(hashmap! {
                    "Ready" => "True",
                    "Available" => "True",
                    "CertificatesAvailable" => "True",
                    "ControlPlaneComponentsHealthy" => "True",
                    "EtcdClusterHealthy" => "True",
                    "MachinesCreated" => "True",
                    "MachinesReady" => "True",
                    "Resized" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(cluster.is_ready(), true);
    }

    #[test]
    fn test_machine_is_ready_when_healthy() {
        let machine = Machine {
            status: Some(MachineStatus {
                conditions: build_conditions(hashmap! {
                    "NodeHealthy" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(machine.is_ready(), true);
    }

    #[test]
    fn test_machine_is_not_ready_when_unhealthy() {
        let machine = Machine {
            status: Some(MachineStatus {
                conditions: build_conditions(hashmap! {
                    "NodeHealthy" => "False",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(machine.is_ready(), false);
    }

    #[test]
    fn test_machine_is_not_ready_when_no_condition() {
        let machine = Machine {
            status: Some(MachineStatus::default()),
            ..Default::default()
        };

        assert_eq!(machine.is_ready(), false);
    }

    #[test]
    fn test_machine_is_not_ready_with_other_conditions() {
        let machine = Machine {
            status: Some(MachineStatus {
                conditions: build_conditions(hashmap! {
                    "InfrastructureReady" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(machine.is_ready(), false);
    }

    #[test]
    fn test_machine_is_not_ready_with_no_status() {
        let machine = Machine::default();

        assert_eq!(machine.is_ready(), false);
    }

    #[test]
    fn test_machines_to_health_status_dict() {
        let machines = vec![
            Machine {
                metadata: ObjectMeta {
                    name: Some("kube-yx7ky-default-worker-srknv-6l6l2-9dlcm".to_string()),
                    ..Default::default()
                },
                spec: MachineSpec {
                    infrastructure_ref: ObjectReference {
                        name: Some("kube-yx7ky-default-worker-srknv-6l6l2".to_string()),
                        ..Default::default()
                    },
                    ..Default::default()
                },
                status: Some(MachineStatus {
                    conditions: build_conditions(hashmap! {
                        "NodeHealthy" => "True",
                    }),
                    ..Default::default()
                }),
                ..Default::default()
            },
            Machine {
                metadata: ObjectMeta {
                    name: Some("kube-yx7ky-default-worker-7rs4w-wpcdc-h9ln8".to_string()),
                    ..Default::default()
                },
                spec: MachineSpec {
                    infrastructure_ref: ObjectReference {
                        name: Some("kube-yx7ky-default-worker-7rs4w-wpcdc".to_string()),
                        ..Default::default()
                    },
                    ..Default::default()
                },
                status: Some(MachineStatus {
                    conditions: build_conditions(hashmap! {
                        "NodeHealthy" => "False",
                    }),
                    ..Default::default()
                }),
                ..Default::default()
            },
        ];

        let health_status_reason = machines.to_health_status_reason();

        assert_eq!(
            health_status_reason,
            hashmap! {
                "kube-yx7ky-default-worker-srknv-6l6l2.Ready".to_string() => true,
                "kube-yx7ky-default-worker-7rs4w-wpcdc.Ready".to_string() => false,
            }
        );
    }
}
