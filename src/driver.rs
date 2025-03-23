use crate::{
    addons::{cloud_controller_manager, ClusterAddon},
    clients::kubernetes::{self, ClientHelpers},
    cluster_api::clusterresourcesets::ClusterResourceSet,
    features, magnum,
    resources::ClusterClassBuilder,
    GLOBAL_RUNTIME,
};
use k8s_openapi::api::core::v1::{Namespace, Secret};
use kube::{api::ObjectMeta, Api, Client};
use pyo3::prelude::*;

#[pyclass]
pub struct Driver {
    client: Client,

    // NOTE(mnaser): The following are legacy values that we need to inject
    //               while we are still in the transition phase.
    namespace: String,
    cluster_class_name: String,
}

/// For this driver, the function that are prefixed with `apply_` can always
/// be called as they are idempotent and will not cause any issues if called
/// multiple times.  On the other hand, functions prefixed with `create_` are
/// not idempotent and should only be called once.
impl Driver {
    fn apply_cluster_class(&self, py: Python<'_>) -> Result<(), kubernetes::Error> {
        let metadata = ObjectMeta {
            name: Some(self.cluster_class_name.clone()),
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

        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async move {
                self.client
                    .create_or_update_cluster_resource(Namespace::from(self))
                    .await?;
                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        openstack_cluster_template,
                    )
                    .await?;
                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        openstack_machine_template,
                    )
                    .await?;
                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        kubeadm_control_plane_template,
                    )
                    .await?;
                self.client
                    .create_or_update_namespaced_resource(&self.namespace, kubeadm_config_template)
                    .await?;
                self.client
                    .create_or_update_namespaced_resource(&self.namespace, cluster_class)
                    .await?;

                Ok(())
            })
        })
    }

    fn create_legacy_cluster_resource_set(
        &self,
        py: Python<'_>,
        cluster: &magnum::Cluster,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async {
                // TODO(mnaser): The secret is still being created by the Python
                //               code, we need to move this to Rust.
                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        ClusterResourceSet::from(cluster),
                    )
                    .await?;

                Ok(())
            })
        })
    }

    fn apply_cloud_provider_cluster_resource_set(
        &self,
        py: Python<'_>,
        cluster: &magnum::Cluster,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async {
                let addon = cloud_controller_manager::Addon::new(cluster.clone());

                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        cluster.cloud_provider_secret(&addon)?,
                    )
                    .await?;
                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        cluster.cloud_provider_cluster_resource_set()?,
                    )
                    .await?;

                Ok(())
            })
        })
    }

    fn delete_legacy_cluster_resource_set(
        &self,
        py: Python<'_>,
        cluster: &magnum::Cluster,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async {
                let resource_name = ClusterResourceSet::from(cluster).metadata.name.unwrap();

                self.client
                    .delete_resource(
                        Api::<ClusterResourceSet>::namespaced(self.client.clone(), &self.namespace),
                        &resource_name,
                    )
                    .await?;
                self.client
                    .delete_resource(
                        Api::<Secret>::namespaced(self.client.clone(), &self.namespace),
                        &resource_name,
                    )
                    .await?;

                Ok(())
            })
        })
    }

    fn delete_cloud_provider_cluster_resource_set(
        &self,
        py: Python<'_>,
        cluster: &magnum::Cluster,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async {
                let resource_name = cluster.cloud_provider_resource_name()?;

                self.client
                    .delete_resource(
                        Api::<ClusterResourceSet>::namespaced(self.client.clone(), &self.namespace),
                        &resource_name,
                    )
                    .await?;
                self.client
                    .delete_resource(
                        Api::<Secret>::namespaced(self.client.clone(), &self.namespace),
                        &resource_name,
                    )
                    .await?;

                Ok(())
            })
        })
    }
}

#[pymethods]
impl Driver {
    #[new]
    fn new(namespace: String, cluster_class_name: String) -> Result<Self, kubernetes::Error> {
        let client = GLOBAL_RUNTIME.block_on(async { Client::try_default().await })?;

        Ok(Self {
            client,
            namespace,
            cluster_class_name,
        })
    }

    fn create_cluster(&self, py: Python<'_>, cluster: PyObject) -> PyResult<()> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        self.apply_cluster_class(py)?;
        self.create_legacy_cluster_resource_set(py, &cluster)?;
        self.apply_cloud_provider_cluster_resource_set(py, &cluster)?;

        Ok(())
    }

    fn delete_cluster(&self, py: Python<'_>, cluster: PyObject) -> PyResult<()> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        self.delete_cloud_provider_cluster_resource_set(py, &cluster)?;
        self.delete_legacy_cluster_resource_set(py, &cluster)?;

        Ok(())
    }
}

impl From<&Driver> for Namespace {
    fn from(driver: &Driver) -> Self {
        Namespace {
            metadata: ObjectMeta {
                name: Some(driver.namespace.to_owned()),
                ..Default::default()
            },
            ..Default::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use http::{Request, Response};
    use k8s_openapi::api::core::v1::Namespace;
    use kube::client::Body;
    use pretty_assertions::assert_eq;

    #[tokio::test]
    async fn test_namespace_for_driver() {
        let (mocksvc, _handle) = tower_test::mock::pair::<Request<Body>, Response<Body>>();
        let client = Client::new(mocksvc, "default");

        let cluster = Driver {
            client: client.clone(),
            namespace: "magnum-system".to_owned(),
            cluster_class_name: "sample-cluster-class".to_owned(),
        };

        let namespace = Namespace::from(&cluster);

        assert_eq!(namespace.metadata.name, Some("magnum-system".to_owned()),);
    }
}
