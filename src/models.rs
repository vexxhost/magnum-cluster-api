use crate::client;
use cluster_api_rs::capi_clusterresourceset::{
    ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
    ClusterResourceSetResourcesKind, ClusterResourceSetSpec,
};
use k8s_openapi::api::core::v1::Namespace;
use kube::core::ObjectMeta;
use maplit::btreemap;
use once_cell::sync::Lazy;
use pyo3::prelude::*;
use tokio::runtime::Runtime;

static GLOBAL_RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("Failed to create Tokio runtime")
});

#[pyclass]
pub struct MagnumCluster {
    #[pyo3(get)]
    namespace: String,

    #[pyo3(get)]
    uuid: String,
}

#[pymethods]
impl MagnumCluster {
    #[new]
    #[pyo3(signature = (obj, namespace = "magnum-system"))]
    fn new(py: Python<'_>, obj: PyObject, namespace: &str) -> PyResult<Self> {
        let uuid: String = obj.getattr(py, "uuid")?.extract(py)?;

        Ok(MagnumCluster {
            uuid,
            namespace: namespace.to_string(),
        })
    }

    fn create(&self) -> PyResult<()> {
        let client = client::KubeClient::new()?;

        GLOBAL_RUNTIME.block_on(async move {
            client
                .create_or_update_cluster_resource(Namespace::from(self))
                .await
                .unwrap();
            client
                .create_or_update_namespaced_resource(
                    &self.namespace,
                    ClusterResourceSet::from(self),
                )
                .await
                .unwrap();
        });

        Ok(())
    }

    fn delete(&self) -> PyResult<()> {
        let client = client::KubeClient::new()?;

        GLOBAL_RUNTIME.block_on(async move {
            client
                .delete_cluster_resource(Namespace::from(self))
                .await
                .unwrap()
        });

        Ok(())
    }
}

impl From<&MagnumCluster> for Namespace {
    fn from(cluster: &MagnumCluster) -> Self {
        Namespace {
            metadata: ObjectMeta {
                name: Some(cluster.namespace.to_owned()),
                ..Default::default()
            },
            ..Default::default()
        }
    }
}

impl From<&MagnumCluster> for ClusterResourceSet {
    fn from(cluster: &MagnumCluster) -> Self {
        ClusterResourceSet {
            metadata: ObjectMeta {
                name: Some(cluster.uuid.to_owned()),
                ..Default::default()
            },
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
