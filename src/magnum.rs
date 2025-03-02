use crate::cluster_api::clusterresourcesets::{
    ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
    ClusterResourceSetResourcesKind, ClusterResourceSetSpec,
};
use k8s_openapi::api::core::v1::ConfigMap;
use kube::api::ObjectMeta;
use maplit::btreemap;
use pyo3::prelude::*;
use serde::Deserialize;
use typed_builder::TypedBuilder;

#[derive(Clone, Default, Deserialize, TypedBuilder)]
pub struct ClusterLabels {
    /// The prefix of the container images to use for the cluster, which
    /// defaults to the upstream images if not set.
    #[builder(default)]
    pub container_infra_prefix: Option<String>,

    /// The tag of the Cilium container image to use for the cluster.
    #[builder(default="v1.15.3".to_owned())]
    pub cilium_tag: String,

    /// The IP address range to use for the Cilium IPAM pool.
    #[builder(default="10.100.0.0/16".to_owned())]
    pub cilium_ipv4pool: String
}

#[pyclass]
#[derive(Clone)]
pub struct Cluster {
    pub uuid: String,
    pub labels: ClusterLabels,
}

impl From<Cluster> for ObjectMeta {
    fn from(cluster: Cluster) -> Self {
        ObjectMeta {
            name: Some(cluster.uuid),
            ..Default::default()
        }
    }
}

impl From<Cluster> for ClusterResourceSet {
    fn from(cluster: Cluster) -> Self {
        ClusterResourceSet {
            metadata: cluster.clone().into(),
            spec: ClusterResourceSetSpec {
                cluster_selector: ClusterResourceSetClusterSelector {
                    match_labels: Some(btreemap! {
                        "cluster-uuid".to_owned() => cluster.uuid.to_owned(),
                    }),
                    match_expressions: None,
                },
                resources: Some(vec![ClusterResourceSetResources {
                    kind: ClusterResourceSetResourcesKind::ConfigMap,
                    name: cluster.uuid.to_owned(),
                }]),
                strategy: None,
            },
            status: None,
        }
    }
}

impl From<Cluster> for ConfigMap {
    fn from(cluster: Cluster) -> Self {
        ConfigMap {
            metadata: cluster.clone().into(),
            ..Default::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;
    use rstest::rstest;
    use serde::Serialize;
    use serde_yaml::Value;
    use std::path::PathBuf;

    const CLUSTER_SCOPED_RESOURCES: &[&str] = &[
        "APIServer",
        "CSIDriver",
        "ClusterRole",
        "ClusterRoleBinding",
        "Installation",
        "StorageClass",
    ];

    #[test]
    fn test_object_meta_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
        };

        let object_meta: ObjectMeta = cluster.into();

        assert_eq!(object_meta.name, Some("sample-uuid".into()));
    }

    #[test]
    fn test_cluster_resource_set_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
        };

        let crs: ClusterResourceSet = cluster.clone().into();

        assert_eq!(crs.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            crs.spec.cluster_selector.match_labels,
            Some(btreemap! {
                "cluster-uuid".to_owned() => cluster.uuid.clone(),
            }),
        );

        assert_eq!(
            crs.spec.resources,
            Some(vec![ClusterResourceSetResources {
                kind: ClusterResourceSetResourcesKind::ConfigMap,
                name: cluster.uuid.clone(),
            }])
        );
    }

    #[rstest]
    fn test_helm_charts_render_with_namespace(
        #[files("magnum_cluster_api/charts/*")]
        #[exclude("patches")]
        path: PathBuf,
    ) {
        #[derive(Serialize)]
        struct Values {}
        let values = Values {};

        let docs = helm::template(
            &path,
            path.file_name().unwrap().to_str().unwrap(),
            "magnum-system",
            &values,
        );
        assert!(
            docs.is_ok(),
            "failed to render chart: {}",
            docs.unwrap_err()
        );

        for doc in docs.unwrap() {
            if CLUSTER_SCOPED_RESOURCES.contains(&doc.get("kind").unwrap().as_str().unwrap()) {
                continue;
            }

            let metadata = doc
                .get("metadata")
                .and_then(|v| v.as_mapping())
                .expect("expected metadata mapping for non-cluster-scoped resource");
            let ns = metadata
                .get(&Value::String("namespace".into()))
                .expect(&format!(
                    "expected namespace field in metadata in document: {:?}",
                    doc
                ));

            assert_eq!(
                ns,
                &Value::String("magnum-system".into()),
                "namespace is not correctly set in document: {:?}",
                doc
            );
        }
    }

    #[test]
    fn test_config_map_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
        };

        let config_map: ConfigMap = cluster.clone().into();

        assert_eq!(config_map.metadata.name, Some(cluster.uuid.clone()));
    }
}
