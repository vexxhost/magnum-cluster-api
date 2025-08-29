use crate::{
    clients::kubernetes::{self, ClientHelpers},
    cluster_api::clusters::Cluster,
};
use backon::{ExponentialBuilder, Retryable};
use kube::{
    api::{Api, DynamicObject, GroupVersionKind},
    core::{gvk::ParseGroupVersionError, GroupVersion},
    Client,
};
use pyo3::{create_exception, exceptions::PyException, prelude::*, types::PyDict, Bound};
use pyo3_async_runtimes::tokio::get_runtime;
use std::{fmt::Debug, str::FromStr};
use thiserror::Error;

create_exception!(magnum_cluster_api, KubeError, PyException);

#[pyclass]
pub struct KubeClient {
    pub client: Client,
}

#[derive(Debug, Error)]
pub enum KubeClientError {
    #[error("Failed to deserialize dictionary: {0}")]
    Parse(#[from] pythonize::PythonizeError),

    #[error("Missing metadata")]
    Metadata,

    #[error("API request failed: {0}")]
    Api(#[from] kube::Error),

    #[error("Failed to parse group version: {0}")]
    ParseGroupVersion(#[from] ParseGroupVersionError),
}

impl From<KubeClientError> for PyErr {
    fn from(err: KubeClientError) -> PyErr {
        PyErr::new::<KubeError, _>(err.to_string())
    }
}

#[pymethods]
impl KubeClient {
    #[new]
    pub fn new() -> Result<Self, kubernetes::Error> {
        let client = get_runtime().block_on(async { Client::try_default().await })?;
        Ok(KubeClient { client })
    }

    #[pyo3(signature = (manifest))]
    fn create_or_update(&self, py: Python<'_>, manifest: &Bound<'_, PyDict>) -> PyResult<()> {
        let object: DynamicObject = pythonize::depythonize(manifest)?;

        let types = object.types.to_owned().ok_or(KubeClientError::Metadata)?;

        let gvk = GroupVersionKind::try_from(types).map_err(KubeClientError::ParseGroupVersion)?;
        let api = self
            .client
            .get_api_from_gvk(&gvk, object.metadata.namespace.as_deref());

        py.allow_threads(|| {
            get_runtime().block_on(async move {
                self.client.create_or_update_resource(api, object).await?;

                Ok(())
            })
        })
    }

    #[pyo3(signature = (namespace, name, manifest))]
    fn update_cluster(
        &self,
        py: Python<'_>,
        namespace: String,
        name: String,
        manifest: &Bound<'_, PyDict>,
    ) -> PyResult<()> {
        let object: Cluster = pythonize::depythonize(manifest)?;
        let api: Api<Cluster> = Api::namespaced(self.client.clone(), &namespace);

        py.allow_threads(|| {
            get_runtime().block_on(async {
                match (|| async {
                    let object = object.clone();
                    let mut remote_object = api.get(&name).await?;

                    remote_object.metadata.labels = object.metadata.labels;
                    remote_object.spec.cluster_network = object.spec.cluster_network;
                    remote_object.spec.topology = object.spec.topology;

                    api.replace(&name, &Default::default(), &remote_object)
                        .await
                })
                .retry(ExponentialBuilder::default())
                .when(|e| matches!(e, kube::Error::Api(api_err) if api_err.code == 409))
                .await
                {
                    Ok(_) => Ok(()),
                    Err(e) => Err(KubeClientError::Api(e)),
                }
            })
        })?;

        Ok(())
    }

    #[pyo3(signature = (api_version, kind, name, namespace=None))]
    fn delete(
        &self,
        py: Python<'_>,
        api_version: &str,
        kind: &str,
        name: &str,
        namespace: Option<&str>,
    ) -> PyResult<()> {
        let gvk: GroupVersionKind = GroupVersion::from_str(api_version)
            .map_err(KubeClientError::ParseGroupVersion)?
            .with_kind(kind);
        let api = self.client.get_api_from_gvk(&gvk, namespace);

        py.allow_threads(|| {
            get_runtime().block_on(async {
                self.client.delete_resource(api, name).await?;

                Ok(())
            })
        })
    }
}
