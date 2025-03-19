use crate::cluster_api::machines::Machine;

pub trait MachineExt {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cluster_api::machines::MachineStatus;
    use k8s_openapi::apimachinery::pkg::apis::meta::v1::{Condition, Time};
    use pretty_assertions::assert_eq;

    #[test]
    fn test_machine_is_ready_when_healthy() {
        let machine = Machine {
            status: Some(MachineStatus {
                conditions: Some(vec![Condition {
                    type_: "NodeHealthy".to_string(),
                    status: "True".to_string(),
                    last_transition_time: Time(k8s_openapi::chrono::Utc::now()),
                    message: "".to_string(),
                    reason: "".to_string(),
                    observed_generation: None,
                }]),
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
                conditions: Some(vec![Condition {
                    type_: "NodeHealthy".to_string(),
                    status: "False".to_string(),
                    last_transition_time: Time(k8s_openapi::chrono::Utc::now()),
                    message: "".to_string(),
                    reason: "".to_string(),
                    observed_generation: None,
                }]),
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
                conditions: Some(vec![Condition {
                    type_: "InfrastructureReady".to_string(),
                    status: "True".to_string(),
                    last_transition_time: Time(k8s_openapi::chrono::Utc::now()),
                    message: "".to_string(),
                    reason: "".to_string(),
                    observed_generation: None,
                }]),
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
}
