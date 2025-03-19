use crate::{
    addons::{cilium, cloud_controller_manager, ClusterAddon},
    cluster_api::clusterresourcesets::{
        ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
        ClusterResourceSetResourcesKind, ClusterResourceSetSpec,
    },
};
use k8s_openapi::api::core::v1::Secret;
use kube::api::ObjectMeta;
use maplit::btreemap;
use pyo3::prelude::*;
use serde::Deserialize;
use std::collections::BTreeMap;
use typed_builder::TypedBuilder;

#[derive(Clone, Deserialize, FromPyObject)]
pub struct ClusterTemplate {
    pub network_driver: String,
}

#[derive(Clone, Default, Deserialize, FromPyObject, TypedBuilder)]
#[pyo3(from_item_all)]
pub struct ClusterLabels {
    /// The prefix of the container images to use for the cluster, which
    /// defaults to the upstream images if not set.
    #[builder(default)]
    #[pyo3(default)]
    pub container_infra_prefix: Option<String>,

    /// The tag of the Cilium container image to use for the cluster.
    #[builder(default="v1.15.3".to_owned())]
    #[pyo3(default="v1.15.3".to_owned())]
    pub cilium_tag: String,

    /// The IP address range to use for the Cilium IPAM pool.
    #[builder(default="10.100.0.0/16".to_owned())]
    #[pyo3(default="10.100.0.0/16".to_owned())]
    pub cilium_ipv4pool: String,

    /// The tag to use for the OpenStack cloud controller provider
    /// when bootstrapping the cluster.
    #[builder(default="v1.30.0".to_owned())]
    #[pyo3(default="v1.30.0".to_owned())]
    pub cloud_provider_tag: String,

    /// The Kubernetes version to use for the cluster.
    #[builder(default="v1.30.0".to_owned())]
    pub kube_tag: String,
}

#[derive(Clone, Deserialize, FromPyObject)]
pub struct Cluster {
    pub uuid: String,
    pub cluster_template: ClusterTemplate,
    pub stack_id: Option<String>,
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
                    kind: ClusterResourceSetResourcesKind::Secret,
                    name: cluster.uuid.to_owned(),
                }]),
                strategy: None,
            },
            status: None,
        }
    }
}

impl From<Cluster> for Secret {
    fn from(cluster: Cluster) -> Self {
        let mut data = BTreeMap::<String, String>::new();

        // TODO(mnaser): Implement an inventory of addons
        let ccm = cloud_controller_manager::Addon::new(cluster.clone());
        if ccm.enabled() {
            data.insert(
                "cloud-controller-manager.yaml".to_owned(),
                ccm.manifests(
                    &cloud_controller_manager::CloudControllerManagerValues::try_from(
                        cluster.clone(),
                    )
                    .unwrap(),
                )
                .unwrap(),
            );
        }

        let cilium = cilium::Addon::new(cluster.clone());
        if cilium.enabled() {
            data.insert(
                "cilium.yaml".to_owned(),
                cilium
                    .manifests(&cilium::CiliumValues::try_from(cluster.clone()).unwrap())
                    .unwrap(),
            );
        }

        Secret {
            metadata: cluster.clone().into(),
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(data),
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
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let object_meta: ObjectMeta = cluster.into();

        assert_eq!(object_meta.name, Some("sample-uuid".into()));
    }

    #[test]
    fn test_cluster_resource_set_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
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
                kind: ClusterResourceSetResourcesKind::Secret,
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

        let docs = docs.unwrap();
        let docs: Vec<serde_yaml::Value> = serde_yaml::Deserializer::from_str(&docs)
            .map(serde_yaml::Value::deserialize)
            .collect::<Result<_, _>>()
            .expect("failed to parse rendered documents");

        for doc in docs {
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
    fn test_secret_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let secret: Secret = cluster.clone().into();

        assert_eq!(secret.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            secret.type_,
            Some("addons.cluster.x-k8s.io/resource-set".into())
        );
    }
}
