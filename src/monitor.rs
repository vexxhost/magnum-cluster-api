use crate::{
    clients::kubernetes,
    cluster_api::{kubeadmcontrolplane::KubeadmControlPlane, machines::Machine},
    magnum,
};
use k8s_openapi::apimachinery::pkg::apis::meta::v1::{Condition, LabelSelector};
use kube::{api::ListParams, Api};
use maplit::btreemap;
use pyo3::{create_exception, exceptions::PyException, prelude::*, types::PyDict};
use pyo3_async_runtimes::tokio::get_runtime;
use std::collections::BTreeMap;
use thiserror::Error;

const MAX_HEALTH_REASON_LENGTH: usize = 512;

fn find_condition<'a>(
    conditions: Option<&'a [Condition]>,
    condition_type: &str,
) -> Option<&'a Condition> {
    conditions?
        .iter()
        .find(|condition| condition.type_ == condition_type)
}

trait KubeadmControlPlaneExt {
    fn is_ready(&self) -> bool;
}

impl KubeadmControlPlaneExt for KubeadmControlPlane {
    fn is_ready(&self) -> bool {
        self.status
            .as_ref()
            .and_then(|status| {
                status
                    .v1beta2
                    .as_ref()
                    .and_then(|v1beta2| find_condition(v1beta2.conditions.as_deref(), "Available"))
                    .or_else(|| find_condition(status.conditions.as_deref(), "Available"))
            })
            .map(|condition| condition.status == "True")
            .unwrap_or(false)
    }
}

trait MachineExt {
    fn ready_condition(&self) -> Option<&Condition>;
    fn is_ready(&self) -> bool;
    fn status_reason(&self) -> Option<String>;
}

impl MachineExt for Machine {
    fn ready_condition(&self) -> Option<&Condition> {
        self.status.as_ref().and_then(|status| {
            status
                .v1beta2
                .as_ref()
                .and_then(|v1beta2| find_condition(v1beta2.conditions.as_deref(), "Ready"))
                .or_else(|| find_condition(status.conditions.as_deref(), "Ready"))
                .or_else(|| find_condition(status.conditions.as_deref(), "NodeHealthy"))
        })
    }

    fn is_ready(&self) -> bool {
        self.ready_condition()
            .map(|condition| condition.status == "True")
            .unwrap_or(false)
    }

    fn status_reason(&self) -> Option<String> {
        let condition = self.ready_condition()?;
        if condition.status == "True" {
            return None;
        }

        let reason = condition.reason.trim();
        let message = condition.message.trim();
        let detail = match (reason.is_empty(), message.is_empty()) {
            (false, false) => format!("{reason}: {message}"),
            (false, true) => reason.to_string(),
            (true, false) => message.to_string(),
            (true, true) => return None,
        };

        if detail.chars().count() <= MAX_HEALTH_REASON_LENGTH {
            return Some(detail);
        }

        let mut truncated = detail
            .chars()
            .take(MAX_HEALTH_REASON_LENGTH - 3)
            .collect::<String>();
        truncated.push_str("...");
        Some(truncated)
    }
}

struct MachineHealthStatusReason(BTreeMap<String, String>);

impl<'py> IntoPyObject<'py> for MachineHealthStatusReason {
    type Target = PyDict;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let dict = PyDict::new(py);

        for (name, value) in self.0 {
            dict.set_item(name, value)?;
        }

        Ok(dict)
    }
}

trait MachineListExt {
    fn to_health_status_reason(&self) -> MachineHealthStatusReason;
}

impl MachineListExt for [Machine] {
    fn to_health_status_reason(&self) -> MachineHealthStatusReason {
        let mut status = BTreeMap::new();

        for machine in self {
            let Some(name) = machine.spec.infrastructure_ref.name.as_ref() else {
                continue;
            };

            let is_ready = machine.is_ready();
            status.insert(
                format!("{name}.Ready"),
                if is_ready { "True" } else { "False" }.to_string(),
            );

            if !is_ready {
                if let Some(reason) = machine.status_reason() {
                    status.insert(format!("{name}.Reason"), reason);
                }
            }
        }

        MachineHealthStatusReason(status)
    }
}

create_exception!(magnum_cluster_api, PyMonitorError, PyException);

#[derive(Debug, Error)]
enum MonitorError {
    #[error("Failed to parse label selector: {0}")]
    ParseLabelSelector(#[from] kube::core::ParseExpressionError),

    #[error("Failed to get machines: {0}")]
    GetMachines(kube::Error),

    #[error("Failed to get KubeadmControlPlane: {0}")]
    GetKubeadmControlPlane(kube::Error),

    #[error("Failed to get find KubeadmControlPlane: {0}")]
    NoKubeadmControlPlane(String),
}

impl From<MonitorError> for PyErr {
    fn from(err: MonitorError) -> PyErr {
        PyErr::new::<PyMonitorError, _>(err.to_string())
    }
}

#[pyclass]
pub struct Monitor {
    client: kube::Client,
    cluster: magnum::Cluster,
}

#[pymethods]
impl Monitor {
    #[new]
    #[pyo3(signature = (cluster))]
    fn new(py: Python<'_>, cluster: Py<PyAny>) -> PyResult<Self> {
        let client = kubernetes::shared_client()?;
        let cluster: magnum::Cluster = cluster.extract(py)?;
        Ok(Self { client, cluster })
    }

    fn poll_health_status(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let data = PyDict::new(py);
        let health_status_reason = PyDict::new(py);

        data.set_item("health_status", "UNKNOWN")?;
        data.set_item("health_status_reason", health_status_reason)?;

        let stack_id = match &self.cluster.stack_id {
            Some(id) => id,
            None => {
                return Ok(data.into());
            }
        };

        let list_params = ListParams::default().labels_from(
            &LabelSelector {
                match_labels: Some(btreemap! {
                    "cluster.x-k8s.io/cluster-name".to_string() => stack_id.to_string(),
                }),
                ..Default::default()
            }
            .try_into()
            .map_err(MonitorError::ParseLabelSelector)?,
        );

        let machine_api: Api<Machine> = Api::namespaced(self.client.clone(), "magnum-system");
        let kcp_api: Api<KubeadmControlPlane> =
            Api::namespaced(self.client.clone(), "magnum-system");

        let (machines, kcp_list) = Python::detach(py, || {
            get_runtime().block_on(async {
                futures::join!(machine_api.list(&list_params), kcp_api.list(&list_params))
            })
        });

        let machines = machines.map_err(MonitorError::GetMachines)?;
        let kcp = kcp_list
            .map_err(MonitorError::GetKubeadmControlPlane)?
            .items
            .into_iter()
            .next()
            .ok_or_else(|| MonitorError::NoKubeadmControlPlane(stack_id.to_string()))?;

        let is_healthy = kcp.is_ready() && machines.items.iter().all(|machine| machine.is_ready());
        data.set_item(
            "health_status",
            if is_healthy { "HEALTHY" } else { "UNHEALTHY" },
        )?;

        let health_status_reason = machines.items.to_health_status_reason().into_pyobject(py)?;
        health_status_reason.set_item("api", if kcp.is_ready() { "ok" } else { "nok" })?;
        data.set_item("health_status_reason", health_status_reason)?;

        Ok(data.into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cluster_api::{
        kubeadmcontrolplane::{KubeadmControlPlaneStatus, KubeadmControlPlaneStatusV1beta2},
        machines::{MachineSpec, MachineStatus, MachineStatusV1beta2},
    };
    use k8s_openapi::{
        api::core::v1::ObjectReference,
        apimachinery::pkg::apis::meta::v1::{Condition, Time},
    };
    use kube::api::ObjectMeta;
    use maplit::{btreemap, hashmap};
    use pretty_assertions::assert_eq;
    use std::collections::HashMap;

    fn build_conditions(conditions: HashMap<&str, &str>) -> Option<Vec<Condition>> {
        Some(
            conditions
                .iter()
                .map(|(type_, status)| Condition {
                    type_: type_.to_string(),
                    status: status.to_string(),
                    last_transition_time: Time(k8s_openapi::jiff::Timestamp::now()),
                    message: "".to_string(),
                    reason: "".to_string(),
                    observed_generation: None,
                })
                .collect::<Vec<_>>(),
        )
        .filter(|vec| !vec.is_empty())
    }

    fn build_condition(type_: &str, status: &str, reason: &str, message: &str) -> Condition {
        Condition {
            type_: type_.to_string(),
            status: status.to_string(),
            last_transition_time: Time(k8s_openapi::jiff::Timestamp::now()),
            message: message.to_string(),
            reason: reason.to_string(),
            observed_generation: None,
        }
    }

    #[test]
    fn test_kcp_is_ready_when_available_condition_is_true() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
                conditions: build_conditions(hashmap! {
                    "Available" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert!(kcp.is_ready());
    }

    #[test]
    fn test_kcp_prefers_v1beta2_available_condition() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
                conditions: build_conditions(hashmap! {
                    "Available" => "True",
                }),
                v1beta2: Some(KubeadmControlPlaneStatusV1beta2 {
                    conditions: build_conditions(hashmap! {
                        "Available" => "False",
                    }),
                    ..Default::default()
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(kcp.is_ready(), false);
    }

    #[test]
    fn test_kcp_is_not_ready_when_available_condition_is_false() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
                conditions: build_conditions(hashmap! {
                    "Available" => "False",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(kcp.is_ready(), false);
    }

    #[test]
    fn test_kcp_is_not_ready_when_available_condition_not_present() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
                conditions: build_conditions(hashmap! {
                    "Ready" => "True",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(kcp.is_ready(), false);
    }

    #[test]
    fn test_kcp_is_not_ready_when_conditions_empty() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
                conditions: Some(vec![]),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(kcp.is_ready(), false);
    }

    #[test]
    fn test_kcp_is_not_ready_when_conditions_none() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
                conditions: build_conditions(hashmap! {}),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(kcp.is_ready(), false);
    }

    #[test]
    fn test_kcp_is_not_ready_when_status_none() {
        let kcp = KubeadmControlPlane {
            status: None,
            ..Default::default()
        };

        assert_eq!(kcp.is_ready(), false);
    }

    #[test]
    fn test_kcp_multiple_conditions_only_cares_about_available() {
        let kcp = KubeadmControlPlane {
            status: Some(KubeadmControlPlaneStatus {
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

        assert_eq!(kcp.is_ready(), true);
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
    fn test_machine_prefers_v1beta2_ready_condition() {
        let machine = Machine {
            status: Some(MachineStatus {
                conditions: build_conditions(hashmap! {
                    "Ready" => "True",
                    "NodeHealthy" => "True",
                }),
                v1beta2: Some(MachineStatusV1beta2 {
                    conditions: Some(vec![build_condition(
                        "Ready",
                        "False",
                        "FloatingIPError",
                        "floating ip pool not found",
                    )]),
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(machine.is_ready(), false);
        assert_eq!(
            machine.status_reason(),
            Some("FloatingIPError: floating ip pool not found".to_string())
        );
    }

    #[test]
    fn test_machine_falls_back_to_legacy_ready_condition() {
        let machine = Machine {
            status: Some(MachineStatus {
                conditions: build_conditions(hashmap! {
                    "Ready" => "True",
                    "NodeHealthy" => "False",
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        assert_eq!(machine.is_ready(), true);
    }

    #[test]
    fn test_machine_status_reason_is_bounded_by_characters() {
        let machine = Machine {
            status: Some(MachineStatus {
                v1beta2: Some(MachineStatusV1beta2 {
                    conditions: Some(vec![build_condition(
                        "Ready",
                        "False",
                        "WaitingForInfrastructure",
                        &"界".repeat(MAX_HEALTH_REASON_LENGTH),
                    )]),
                }),
                ..Default::default()
            }),
            ..Default::default()
        };

        let reason = machine.status_reason().unwrap();
        assert_eq!(reason.chars().count(), MAX_HEALTH_REASON_LENGTH);
        assert!(reason.ends_with("..."));
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
                    v1beta2: Some(MachineStatusV1beta2 {
                        conditions: Some(vec![build_condition(
                            "Ready",
                            "False",
                            "FloatingIPError",
                            "floating ip pool not found",
                        )]),
                    }),
                    ..Default::default()
                }),
                ..Default::default()
            },
        ];

        let health_status_reason = machines.to_health_status_reason();

        assert_eq!(
            health_status_reason.0,
            btreemap! {
                "kube-yx7ky-default-worker-srknv-6l6l2.Ready".to_string() => "True".to_string(),
                "kube-yx7ky-default-worker-7rs4w-wpcdc.Ready".to_string() => "False".to_string(),
                "kube-yx7ky-default-worker-7rs4w-wpcdc.Reason".to_string() =>
                    "FloatingIPError: floating ip pool not found".to_string(),
            }
        );
    }
}
