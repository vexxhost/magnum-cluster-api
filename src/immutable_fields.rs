use crate::cluster_api::openstackclusters::OpenStackCluster;
use jsonptr::{assign::Assign, resolve::Resolve, Pointer};
use k8s_openapi::NamespaceResourceScope;
use kube::{
    api::ListParams,
    core::{Expression, Selector},
    Api, Client, Resource,
};
use serde::de::DeserializeOwned;
use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;
use std::fmt::Debug;
use std::marker::PhantomData;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("invalid JSON pointer {pointer:?}: {source}")]
    InvalidPointer {
        pointer: &'static str,
        source: jsonptr::ParseError,
    },
    #[error("failed to assign {pointer:?}: {source}")]
    Assign {
        pointer: &'static str,
        source: jsonptr::assign::Error,
    },
    #[error("kubernetes API error: {0}")]
    Kube(#[from] kube::Error),
    #[error("failed to serialize resource: {0}")]
    Serialize(#[from] serde_json::Error),
    #[error("expected at most 1 {kind} for cluster {cluster_name:?}, found {count}")]
    AmbiguousResource {
        kind: String,
        cluster_name: String,
        count: usize,
    },
}

fn parse_pointer(path: &'static str) -> Result<&'static Pointer, Error> {
    Pointer::parse(path).map_err(|e| Error::InvalidPointer {
        pointer: path,
        source: e,
    })
}

struct FieldMapping {
    resource_path: &'static str,
    variable_path: &'static str,
    label: &'static str,
    /// Optional companion variable that is set to `true` whenever
    /// `resource_path` is present on the existing resource.
    ///
    /// This is required for fields whose ClusterClass patch is gated by an
    /// `enabledIf` guard: simply propagating the existing value into
    /// `variable_path` is not enough, because the patch will not fire when
    /// the guard evaluates to falsy, leaving the generated spec without
    /// the field. The CAPO webhook then blocks the update because it treats
    /// a nil → <value> (or <value> → nil) transition as an immutability
    /// violation (see
    /// `pkg/webhooks/openstackcluster_webhook.go::ValidateUpdate` which
    /// falls back to `reflect.DeepEqual`).
    presence_variable_path: Option<&'static str>,
}

impl FieldMapping {
    fn apply(
        &self,
        existing: &Value,
        labels: &HashMap<String, String>,
        mut variables: Value,
    ) -> Result<Value, Error> {
        let existing_value = existing.resolve(parse_pointer(self.resource_path)?).ok();

        if let Some(presence_path) = self.presence_variable_path {
            if existing_value.is_some() {
                variables
                    .assign(parse_pointer(presence_path)?, Value::Bool(true))
                    .map_err(|e| Error::Assign {
                        pointer: presence_path,
                        source: e,
                    })?;
            }
        }

        let value = if let Some(v) = existing_value {
            v.clone()
        } else if let Some(label_val) = labels.get(self.label) {
            Value::String(label_val.clone())
        } else {
            return Ok(variables);
        };
        variables
            .assign(parse_pointer(self.variable_path)?, value)
            .map_err(|e| Error::Assign {
                pointer: self.variable_path,
                source: e,
            })?;
        Ok(variables)
    }
}

pub struct ResourceFieldMappings<T> {
    fields: &'static [FieldMapping],
    _resource: PhantomData<T>,
}

impl<T> ResourceFieldMappings<T>
where
    T: Resource<DynamicType = (), Scope = NamespaceResourceScope>
        + DeserializeOwned
        + Clone
        + Debug
        + Serialize,
{
    fn apply(
        &self,
        existing: &Value,
        labels: &HashMap<String, String>,
        variables: Value,
    ) -> Result<Value, Error> {
        self.fields
            .iter()
            .try_fold(variables, |vars, field| field.apply(existing, labels, vars))
    }

    pub async fn resolve(
        &self,
        client: &Client,
        namespace: &str,
        cluster_name: &str,
        labels: &HashMap<String, String>,
        variables: Value,
    ) -> Result<Value, Error> {
        let api: Api<T> = Api::namespaced(client.clone(), namespace);
        let selector = Selector::from(Expression::Equal(
            "cluster.x-k8s.io/cluster-name".into(),
            cluster_name.into(),
        ));
        let lp = ListParams::default().labels_from(&selector);

        let list = api.list(&lp).await?;
        let existing: Value = match list.items.len() {
            0 => Value::Null,
            1 => serde_json::to_value(&list.items[0])?,
            count => {
                return Err(Error::AmbiguousResource {
                    kind: T::kind(&()).to_string(),
                    cluster_name: cluster_name.to_owned(),
                    count,
                })
            }
        };

        self.apply(&existing, labels, variables)
    }
}

pub const OPENSTACK_CLUSTER_FIELDS: ResourceFieldMappings<OpenStackCluster> =
    ResourceFieldMappings {
        fields: &[
            FieldMapping {
                resource_path: "/spec/apiServerLoadBalancer/provider",
                variable_path: "/apiServerLoadBalancer/provider",
                label: "octavia_provider",
                presence_variable_path: None,
            },
            FieldMapping {
                resource_path: "/spec/apiServerLoadBalancer/flavor",
                variable_path: "/apiServerLoadBalancer/flavor",
                label: "api_server_lb_flavor",
                presence_variable_path: None,
            },
            FieldMapping {
                resource_path: "/spec/apiServerLoadBalancer/availabilityZone",
                variable_path: "/apiServerLoadBalancer/availabilityZone",
                label: "api_server_lb_availability_zone",
                presence_variable_path: None,
            },
            // Preserve `disableAPIServerFloatingIP` so that upgrades from old
            // magnum-cluster-api versions (pre-v0.25.x) which unconditionally
            // patched this field do not hit CAPO's immutability webhook.
            //
            // `presence_variable_path` forces the ClusterClass patch to fire
            // whenever the existing OpenStackCluster already has this field
            // set, even if the user's label-derived intent would otherwise
            // skip the patch.
            FieldMapping {
                resource_path: "/spec/disableAPIServerFloatingIP",
                variable_path: "/disableAPIServerFloatingIP",
                label: "",
                presence_variable_path: Some("/disableAPIServerFloatingIPManaged"),
            },
        ],
        _resource: PhantomData,
    };

#[cfg(test)]
mod tests {
    use super::*;
    use maplit::hashmap;
    use serde_json::json;

    mod parse_pointer {
        use super::*;

        #[test]
        fn valid_json_pointer() {
            assert!(parse_pointer("/spec/apiServerLoadBalancer/provider").is_ok());
        }

        #[test]
        fn missing_leading_slash_returns_error() {
            assert!(matches!(
                parse_pointer("no-slash"),
                Err(Error::InvalidPointer { .. })
            ));
        }
    }

    mod field_mapping {
        use super::*;
        use pretty_assertions::assert_eq;

        const PROVIDER: FieldMapping = FieldMapping {
            resource_path: "/spec/apiServerLoadBalancer/provider",
            variable_path: "/apiServerLoadBalancer/provider",
            label: "octavia_provider",
            presence_variable_path: None,
        };

        #[test]
        fn existing_resource_value_takes_priority_over_label() {
            let existing = json!({"spec": {"apiServerLoadBalancer": {"provider": "amphora"}}});
            let labels = hashmap! { "octavia_provider".into() => "ovn".into() };

            let result = PROVIDER
                .apply(&existing, &labels, json!({}))
                .expect("apply failed");

            assert_eq!(result, json!({"apiServerLoadBalancer": {"provider": "amphora"}}));
        }

        #[test]
        fn falls_back_to_label_when_resource_field_missing() {
            let labels = hashmap! { "octavia_provider".into() => "ovn".into() };

            let result = PROVIDER
                .apply(&Value::Null, &labels, json!({}))
                .expect("apply failed");

            assert_eq!(result, json!({"apiServerLoadBalancer": {"provider": "ovn"}}));
        }

        #[test]
        fn skips_when_neither_resource_nor_label_present() {
            let result = PROVIDER
                .apply(&Value::Null, &HashMap::new(), json!({}))
                .expect("apply failed");

            assert_eq!(result, json!({}));
        }

        #[test]
        fn preserves_existing_variables() {
            let existing = json!({"spec": {"apiServerLoadBalancer": {"provider": "amphora"}}});

            let result = PROVIDER
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({"apiServerLoadBalancer": {"enabled": true}}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({"apiServerLoadBalancer": {"enabled": true, "provider": "amphora"}})
            );
        }
    }

    mod openstack_cluster_existing {
        use super::*;
        use pretty_assertions::assert_eq;

        #[test]
        fn preserves_lb_provider() {
            let existing = json!({"spec": {"apiServerLoadBalancer": {"provider": "amphora"}}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({"apiServerLoadBalancer": {"enabled": true}}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({"apiServerLoadBalancer": {"enabled": true, "provider": "amphora"}})
            );
        }

        #[test]
        fn preserves_lb_flavor() {
            let existing = json!({"spec": {"apiServerLoadBalancer": {"flavor": "lb-small"}}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({"apiServerLoadBalancer": {"enabled": true}}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({"apiServerLoadBalancer": {"enabled": true, "flavor": "lb-small"}})
            );
        }

        #[test]
        fn preserves_lb_availability_zone() {
            let existing =
                json!({"spec": {"apiServerLoadBalancer": {"availabilityZone": "az1"}}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({"apiServerLoadBalancer": {"enabled": true}}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({"apiServerLoadBalancer": {"enabled": true, "availabilityZone": "az1"}})
            );
        }

        #[test]
        fn preserves_all_lb_fields() {
            let existing = json!({
                "spec": {
                    "apiServerLoadBalancer": {
                        "provider": "amphora",
                        "flavor": "lb-small",
                        "availabilityZone": "az1"
                    }
                }
            });

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({"apiServerLoadBalancer": {"enabled": true}}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "apiServerLoadBalancer": {
                        "enabled": true,
                        "provider": "amphora",
                        "flavor": "lb-small",
                        "availabilityZone": "az1"
                    }
                })
            );
        }

        #[test]
        fn existing_resource_wins_over_labels() {
            let existing = json!({
                "spec": {
                    "apiServerLoadBalancer": {
                        "provider": "amphora",
                        "flavor": "lb-small",
                        "availabilityZone": "az1"
                    }
                }
            });
            let labels = hashmap! {
                "octavia_provider".into() => "ovn".into(),
                "api_server_lb_flavor".into() => "lb-large".into(),
                "api_server_lb_availability_zone".into() => "az9".into(),
            };

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &labels,
                    json!({"apiServerLoadBalancer": {"enabled": true}}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "apiServerLoadBalancer": {
                        "enabled": true,
                        "provider": "amphora",
                        "flavor": "lb-small",
                        "availabilityZone": "az1"
                    }
                })
            );
        }
    }

    mod openstack_cluster_new {
        use super::*;
        use pretty_assertions::assert_eq;

        #[test]
        fn lb_provider_from_label() {
            let labels = hashmap! { "octavia_provider".into() => "ovn".into() };

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&Value::Null, &labels, json!({}))
                .expect("apply failed");

            assert_eq!(result, json!({"apiServerLoadBalancer": {"provider": "ovn"}}));
        }

        #[test]
        fn lb_flavor_from_label() {
            let labels = hashmap! { "api_server_lb_flavor".into() => "lb-tiny".into() };

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&Value::Null, &labels, json!({}))
                .expect("apply failed");

            assert_eq!(
                result,
                json!({"apiServerLoadBalancer": {"flavor": "lb-tiny"}})
            );
        }

        #[test]
        fn lb_availability_zone_from_label() {
            let labels =
                hashmap! { "api_server_lb_availability_zone".into() => "az2".into() };

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&Value::Null, &labels, json!({}))
                .expect("apply failed");

            assert_eq!(
                result,
                json!({"apiServerLoadBalancer": {"availabilityZone": "az2"}})
            );
        }

        #[test]
        fn no_fields_set_without_labels() {
            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&Value::Null, &HashMap::new(), json!({}))
                .expect("apply failed");

            assert_eq!(result, json!({}));
        }

        #[test]
        fn all_fields_from_labels() {
            let labels = hashmap! {
                "octavia_provider".into() => "ovn".into(),
                "api_server_lb_flavor".into() => "lb-tiny".into(),
                "api_server_lb_availability_zone".into() => "az2".into(),
            };

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&Value::Null, &labels, json!({}))
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "apiServerLoadBalancer": {
                        "provider": "ovn",
                        "flavor": "lb-tiny",
                        "availabilityZone": "az2"
                    }
                })
            );
        }
    }

    mod disable_api_server_floating_ip_preservation {
        //! Regression tests for upgrades from pre-v0.25.x clusters which
        //! always patched `disableAPIServerFloatingIP` on the OpenStackCluster.
        //!
        //! The CAPO webhook treats a change of `disableAPIServerFloatingIP`
        //! (including nil ↔ value) as an immutability violation. When the
        //! existing spec has the field set, we must ensure the ClusterClass
        //! patch fires (via the `disableAPIServerFloatingIPManaged` companion
        //! variable) and carries the pre-existing value through, so the
        //! generated spec is identical to the stored spec.
        use super::*;
        use pretty_assertions::assert_eq;

        #[test]
        fn preserves_false_value_and_sets_managed_flag() {
            let existing = json!({"spec": {"disableAPIServerFloatingIP": false}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&existing, &HashMap::new(), json!({}))
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "disableAPIServerFloatingIP": false,
                    "disableAPIServerFloatingIPManaged": true,
                })
            );
        }

        #[test]
        fn preserves_true_value_and_sets_managed_flag() {
            let existing = json!({"spec": {"disableAPIServerFloatingIP": true}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&existing, &HashMap::new(), json!({}))
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "disableAPIServerFloatingIP": true,
                    "disableAPIServerFloatingIPManaged": true,
                })
            );
        }

        #[test]
        fn missing_field_leaves_managed_flag_unset() {
            // Fresh-install clusters (post-v0.25.x with the default label)
            // have no `disableAPIServerFloatingIP` on the OpenStackCluster
            // spec. We must not flip the managed flag, otherwise the patch
            // would fire and add the field — which CAPO would reject as an
            // immutability violation on subsequent reconciliations.
            let existing = json!({"spec": {}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(&existing, &HashMap::new(), json!({}))
                .expect("apply failed");

            assert_eq!(result, json!({}));
        }

        #[test]
        fn overrides_caller_supplied_variable_when_field_present() {
            // The caller seeds the variables with the label-derived intent
            // (`disableAPIServerFloatingIP = true`). The existing spec says
            // otherwise — existing value must win to keep the spec immutable.
            let existing = json!({"spec": {"disableAPIServerFloatingIP": false}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({"disableAPIServerFloatingIP": true}),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "disableAPIServerFloatingIP": false,
                    "disableAPIServerFloatingIPManaged": true,
                })
            );
        }

        #[test]
        fn preserves_caller_supplied_managed_flag_when_field_absent() {
            // Fresh clusters where the user has asked to disable the floating
            // IP: the caller seeds `disableAPIServerFloatingIPManaged = true`
            // so the patch fires on create. Preservation must not clobber it.
            let existing = json!({"spec": {}});

            let result = OPENSTACK_CLUSTER_FIELDS
                .apply(
                    &existing,
                    &HashMap::new(),
                    json!({
                        "disableAPIServerFloatingIP": true,
                        "disableAPIServerFloatingIPManaged": true,
                    }),
                )
                .expect("apply failed");

            assert_eq!(
                result,
                json!({
                    "disableAPIServerFloatingIP": true,
                    "disableAPIServerFloatingIPManaged": true,
                })
            );
        }
    }
}
