// WARNING: generated by kopium - manual changes will be overwritten
// kopium command: kopium -D Default -D PartialEq -A -d clusterresourcesets.addons.cluster.x-k8s.io
// kopium version: 0.21.1

#[allow(unused_imports)]
mod prelude {
    pub use k8s_openapi::apimachinery::pkg::apis::meta::v1::Condition;
    pub use kube::CustomResource;
    pub use schemars::JsonSchema;
    pub use serde::{Deserialize, Serialize};
    pub use std::collections::BTreeMap;
}
use self::prelude::*;

/// ClusterResourceSetSpec defines the desired state of ClusterResourceSet.
#[derive(CustomResource, Serialize, Deserialize, Clone, Debug, Default, PartialEq, JsonSchema)]
#[kube(
    group = "addons.cluster.x-k8s.io",
    version = "v1beta1",
    kind = "ClusterResourceSet",
    plural = "clusterresourcesets"
)]
#[kube(namespaced)]
#[kube(status = "ClusterResourceSetStatus")]
#[kube(derive = "Default")]
#[kube(derive = "PartialEq")]
pub struct ClusterResourceSetSpec {
    /// Label selector for Clusters. The Clusters that are
    /// selected by this will be the ones affected by this ClusterResourceSet.
    /// It must match the Cluster labels. This field is immutable.
    /// Label selector cannot be empty.
    #[serde(rename = "clusterSelector")]
    pub cluster_selector: ClusterResourceSetClusterSelector,
    /// Resources is a list of Secrets/ConfigMaps where each contains 1 or more resources to be applied to remote clusters.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resources: Option<Vec<ClusterResourceSetResources>>,
    /// Strategy is the strategy to be used during applying resources. Defaults to ApplyOnce. This field is immutable.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub strategy: Option<ClusterResourceSetStrategy>,
}

/// Label selector for Clusters. The Clusters that are
/// selected by this will be the ones affected by this ClusterResourceSet.
/// It must match the Cluster labels. This field is immutable.
/// Label selector cannot be empty.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, JsonSchema)]
pub struct ClusterResourceSetClusterSelector {
    /// matchExpressions is a list of label selector requirements. The requirements are ANDed.
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        rename = "matchExpressions"
    )]
    pub match_expressions: Option<Vec<ClusterResourceSetClusterSelectorMatchExpressions>>,
    /// matchLabels is a map of {key,value} pairs. A single {key,value} in the matchLabels
    /// map is equivalent to an element of matchExpressions, whose key field is "key", the
    /// operator is "In", and the values array contains only "value". The requirements are ANDed.
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        rename = "matchLabels"
    )]
    pub match_labels: Option<BTreeMap<String, String>>,
}

/// A label selector requirement is a selector that contains values, a key, and an operator that
/// relates the key and values.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, JsonSchema)]
pub struct ClusterResourceSetClusterSelectorMatchExpressions {
    /// key is the label key that the selector applies to.
    pub key: String,
    /// operator represents a key's relationship to a set of values.
    /// Valid operators are In, NotIn, Exists and DoesNotExist.
    pub operator: String,
    /// values is an array of string values. If the operator is In or NotIn,
    /// the values array must be non-empty. If the operator is Exists or DoesNotExist,
    /// the values array must be empty. This array is replaced during a strategic
    /// merge patch.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub values: Option<Vec<String>>,
}

/// ResourceRef specifies a resource.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, JsonSchema)]
pub struct ClusterResourceSetResources {
    /// Kind of the resource. Supported kinds are: Secrets and ConfigMaps.
    pub kind: ClusterResourceSetResourcesKind,
    /// Name of the resource that is in the same namespace with ClusterResourceSet object.
    pub name: String,
}

/// ResourceRef specifies a resource.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, JsonSchema)]
pub enum ClusterResourceSetResourcesKind {
    Secret,
    #[default]
    ConfigMap,
}

/// ClusterResourceSetSpec defines the desired state of ClusterResourceSet.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq, JsonSchema)]
pub enum ClusterResourceSetStrategy {
    ApplyOnce,
    Reconcile,
}

/// ClusterResourceSetStatus defines the observed state of ClusterResourceSet.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq, JsonSchema)]
pub struct ClusterResourceSetStatus {
    /// Conditions defines current state of the ClusterResourceSet.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub conditions: Option<Vec<Condition>>,
    /// ObservedGeneration reflects the generation of the most recently observed ClusterResourceSet.
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        rename = "observedGeneration"
    )]
    pub observed_generation: Option<i64>,
}
