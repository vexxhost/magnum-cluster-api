use crate::{
    builder::ClusterClassBuilder,
    client,
    cluster_api::clusterresourcesets::{
        ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
        ClusterResourceSetResourcesKind, ClusterResourceSetSpec,
    },
    features,
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

    fn create_or_update(&self) -> PyResult<()> {
        let client = client::KubeClient::new()?;

        let metadata = ObjectMeta {
            name: Some("test".to_string()),
            namespace: Some(self.namespace.clone()),
            ..Default::default()
        };

        let mut openstack_cluster_template = features::OPENSTACK_CLUSTER_TEMPLATE.clone();
        openstack_cluster_template.metadata = metadata.clone();

        let mut openstack_machine_template = features::OPENSTACK_MACHINE_TEMPLATE.clone();
        openstack_machine_template.metadata = metadata.clone();

        let mut kubeadm_control_plane_template = features::KUBEADM_CONTROL_PLANE_TEMPLATE.clone();
        kubeadm_control_plane_template.metadata = metadata.clone();

        let mut kubeadm_config_template = features::KUBEADM_CONFIG_TEMPLATE.clone();
        kubeadm_config_template.metadata = metadata.clone();

        let cluster_class = ClusterClassBuilder::default(metadata.clone());

        GLOBAL_RUNTIME.block_on(async move {
            // TODO: get rid of the unwraps here
            client
                .create_or_update_cluster_resource(Namespace::from(self))
                .await
                .unwrap();
            client
                .create_or_update_namespaced_resource(&self.namespace, openstack_cluster_template)
                .await
                .unwrap();
            client
                .create_or_update_namespaced_resource(&self.namespace, openstack_machine_template)
                .await
                .unwrap();
            client
                .create_or_update_namespaced_resource(
                    &self.namespace,
                    kubeadm_control_plane_template,
                )
                .await
                .unwrap();
            client
                .create_or_update_namespaced_resource(&self.namespace, kubeadm_config_template)
                .await
                .unwrap();
            client
                .create_or_update_namespaced_resource(&self.namespace, cluster_class)
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
                namespace: Some(cluster.namespace.to_owned()),
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cluster_api::clusterresourcesets::{
        ClusterResourceSet, ClusterResourceSetResourcesKind,
    };
    use k8s_openapi::api::core::v1::Namespace;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_namespace_conversion() {
        let cluster = MagnumCluster {
            uuid: "sample-uuid".to_owned(),
            namespace: "sample-namespace".to_owned(),
        };

        let namespace = Namespace::from(&cluster);

        assert_eq!(namespace.metadata.name, Some("sample-namespace".to_owned()),);
    }

    #[test]
    fn test_cluster_resource_set_conversion() {
        let cluster = MagnumCluster {
            uuid: "sample-uuid".to_owned(),
            namespace: "sample-namespace".to_owned(),
        };

        let crs = ClusterResourceSet::from(&cluster);

        assert_eq!(crs.metadata.namespace, Some(cluster.namespace.clone()));
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
}
