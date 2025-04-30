use std::collections::BTreeMap;

use crate::{
    addons::{self, ClusterAddon},
    clients::kubernetes::{self, ClientHelpers},
    cluster_api::clusterresourcesets::ClusterResourceSet,
    features,
    magnum::{self},
    resources::ClusterClassBuilder,
};
use k8s_openapi::api::core::v1::{Namespace, Secret};
use kube::{api::ObjectMeta, Api, Client};
use pyo3::{prelude::*, types::PyType};
use pyo3_async_runtimes::tokio::get_runtime;

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
    fn create_legacy_cluster_resource_set(
        &self,
        py: Python<'_>,
        cluster: &magnum::Cluster,
    ) -> PyResult<()> {
        py.allow_threads(|| {
            get_runtime().block_on(async {
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
        let addon = addons::cloud_controller_manager::Addon::new(cluster.clone());

        py.allow_threads(|| {
            get_runtime().block_on(async {
                // TODO(mnaser): The secret is still being created by the Python
                //               code, we need to move this to Rust.
                self.client
                    .create_or_update_namespaced_resource(
                        &self.namespace,
                        cluster.cluster_addon_cluster_resource_set(&addon)?,
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
            get_runtime().block_on(async {
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
        let addon = addons::cloud_controller_manager::Addon::new(cluster.clone());

        py.allow_threads(|| {
            get_runtime().block_on(async {
                self.client
                    .delete_resource(
                        Api::<ClusterResourceSet>::namespaced(self.client.clone(), &self.namespace),
                        &addon.secret_name()?,
                    )
                    .await?;
                self.client
                    .delete_resource(
                        Api::<Secret>::namespaced(self.client.clone(), &self.namespace),
                        &addon.secret_name()?,
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
        let client = get_runtime().block_on(async { Client::try_default().await })?;

        Ok(Self {
            client,
            namespace,
            cluster_class_name,
        })
    }

    // TODO(mnaser): We should move this out of the Python-facing implementation once we have
    //               migrated all the code to Rust.
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
            get_runtime().block_on(async move {
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

    // TODO(mnaser): We should move this out of the Python-facing implementation once we have
    //               migrated all the code to Rust.
    #[classmethod]
    #[pyo3(signature = (cluster))]
    fn get_legacy_cluster_resource_secret_data(
        _cls: &Bound<'_, PyType>,
        cluster: PyObject,
        py: Python<'_>,
    ) -> PyResult<Option<BTreeMap<String, String>>> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        Ok(Secret::from(cluster).string_data)
    }

    // TODO(mnaser): We should move this out of the Python-facing implementation once we have
    //               migrated all the code to Rust.
    #[classmethod]
    #[pyo3(signature = (cluster))]
    fn get_cloud_provider_cluster_resource_secret_data(
        _cls: &Bound<'_, PyType>,
        cluster: PyObject,
        py: Python<'_>,
    ) -> PyResult<Option<BTreeMap<String, String>>> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        let cloud_controller_manager =
            addons::cloud_controller_manager::Addon::new(cluster.clone());
        let cinder_csi = addons::cinder_csi::Addon::new(cluster.clone());

        let mut data = BTreeMap::new();

        data.extend(
            cluster
                .cluster_addon_secret(&cloud_controller_manager)?
                .string_data
                .unwrap_or_default(),
        );
        data.extend(
            cluster
                .cluster_addon_secret(&cinder_csi)?
                .string_data
                .unwrap_or_default(),
        );

        Ok(Some(data))
    }

    // TODO(mnaser): We should move this out of the Python-facing implementation once we have
    //               migrated all the code to Rust.
    #[classmethod]
    #[pyo3(signature = (cluster))]
    fn get_cinder_csi_cluster_resource_secret_data(
        _cls: &Bound<'_, PyType>,
        cluster: PyObject,
        py: Python<'_>,
    ) -> PyResult<Option<BTreeMap<String, String>>> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        let addon = addons::cinder_csi::Addon::new(cluster.clone());
        Ok(cluster.cluster_addon_secret(&addon)?.string_data)
    }

    fn create_cluster(&self, py: Python<'_>, cluster: PyObject) -> PyResult<()> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        self.apply_cluster_class(py)?;
        self.create_legacy_cluster_resource_set(py, &cluster)?;
        self.apply_cloud_provider_cluster_resource_set(py, &cluster)?;

        Ok(())
    }

    fn upgrade_cluster(&self, py: Python<'_>, cluster: PyObject) -> PyResult<()> {
        let cluster: magnum::Cluster = cluster.extract(py)?;

        self.apply_cluster_class(py)?;
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
    use crate::clients::kubernetes::fixtures;
    use k8s_openapi::api::core::v1::Namespace;
    use pretty_assertions::assert_eq;

    #[tokio::test]
    async fn test_namespace_for_driver() {
        let (client, api_server) = fixtures::get_test_client();
        api_server.run(fixtures::Scenario::RadioSilence);

        let cluster = Driver {
            client: client.clone(),
            namespace: "magnum-system".to_owned(),
            cluster_class_name: "sample-cluster-class".to_owned(),
        };

        let namespace = Namespace::from(&cluster);

        assert_eq!(namespace.metadata.name, Some("magnum-system".to_owned()),);
    }
}
