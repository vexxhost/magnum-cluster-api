use std::str::FromStr;

use backoff::{future::retry, ExponentialBackoff};
use kube::{
    api::{Api, ApiResource, DynamicObject, GroupVersionKind, PostParams},
    Client, Config, ResourceExt,
};
use kube_core::{gvk::ParseGroupVersionError, GroupVersion};
use once_cell::sync::Lazy;
use pyo3::create_exception;
use pyo3::{exceptions, exceptions::PyException, prelude::*, types::PyDict, Bound};
use thiserror::Error;
use tokio::runtime::Runtime;

create_exception!(magnum_cluster_api, KubeError, PyException);

static GLOBAL_RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("Failed to create Tokio runtime")
});

#[pyclass]
pub struct KubeClient {
    client: Client,
}

#[derive(Debug, Error)]
pub enum KubeClientError {
    #[error("Failed to deserialize dictionary: {0}")]
    ParseError(#[from] pythonize::PythonizeError),

    #[error("Missing metadata")]
    MetadataError,

    #[error("API request failed: {0}")]
    ApiError(#[from] kube::Error),

    #[error("Failed to parse group version: {0}")]
    ParseGroupVersionError(#[from] ParseGroupVersionError),
}

impl From<KubeClientError> for PyErr {
    fn from(err: KubeClientError) -> PyErr {
        PyErr::new::<KubeError, _>(err.to_string())
    }
}

impl KubeClient {
    fn get_api_from_gvk(
        &self,
        gvk: &GroupVersionKind,
        namespace: Option<&str>,
    ) -> Api<DynamicObject> {
        let api_resource = ApiResource::from_gvk(gvk);

        let client = self.client.to_owned();
        let api: Api<DynamicObject> = if api_resource.kind == "Namespace" {
            Api::all_with(client, &api_resource)
        } else {
            Api::namespaced_with(client, namespace.unwrap(), &api_resource)
        };

        api
    }
}

#[pymethods]
impl KubeClient {
    #[new]
    fn new() -> PyResult<Self> {
        let client = GLOBAL_RUNTIME.block_on(async {
            let config = Config::infer()
                .await
                .map_err(|e: kube::config::InferConfigError| {
                    PyErr::new::<exceptions::PyValueError, _>(format!(
                        "Failed to load KUBECONFIG: {}",
                        e
                    ))
                })?;

            Client::try_from(config).map_err(|e| {
                PyErr::new::<exceptions::PyRuntimeError, _>(format!(
                    "Failed to create client: {}",
                    e
                ))
            })
        })?;

        Ok(KubeClient { client })
    }

    #[pyo3(signature = (manifest))]
    fn create_or_update(&self, manifest: &Bound<'_, PyDict>) -> PyResult<()> {
        let object: DynamicObject = pythonize::depythonize(manifest)?;

        let name = object
            .metadata
            .name
            .to_owned()
            .ok_or(KubeClientError::MetadataError)?;

        let types = object
            .types
            .to_owned()
            .ok_or(KubeClientError::MetadataError)?;

        let gvk =
            GroupVersionKind::try_from(types).map_err(KubeClientError::ParseGroupVersionError)?;
        let api = self.get_api_from_gvk(&gvk, object.metadata.namespace.as_deref());

        GLOBAL_RUNTIME.block_on(async move {
            match api.get(&name).await {
                Ok(..) => {
                    retry(ExponentialBackoff::default(), || async {
                        let mut new_object = object.clone();

                        let server_object = api.get(&name).await?;
                        new_object.metadata.resource_version = server_object.resource_version();

                        match api.replace(&name, &Default::default(), &new_object).await {
                            Ok(result) => Ok(result),
                            Err(e) => match e {
                                kube::Error::Api(ref err) if err.code == 409 => {
                                    Err(backoff::Error::transient(e))
                                }
                                _ => Err(backoff::Error::Permanent(e)),
                            },
                        }
                    })
                    .await
                    .map_err(|e| KubeClientError::ApiError(e))?;
                }
                Err(kube::Error::Api(ref err)) if err.code == 404 => {
                    api.create(&PostParams::default(), &object)
                        .await
                        .map_err(|e| KubeClientError::ApiError(e))?;
                }
                Err(e) => {
                    return Err(KubeClientError::ApiError(e))?;
                }
            }

            Ok(())
        })
    }

    #[pyo3(signature = (api_version, kind, name, namespace=None))]
    fn delete(
        &self,
        api_version: &str,
        kind: &str,
        name: &str,
        namespace: Option<&str>,
    ) -> PyResult<()> {
        let gvk: GroupVersionKind = GroupVersion::from_str(api_version)
            .map_err(KubeClientError::ParseGroupVersionError)?
            .with_kind(kind);
        let api = self.get_api_from_gvk(&gvk, namespace);

        GLOBAL_RUNTIME.block_on(async {
            api.delete(name, &Default::default())
                .await
                .map_err(|e| KubeClientError::ApiError(e))?;

            Ok(())
        })
    }
}
