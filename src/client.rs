use crate::{cluster_api::clusters::Cluster, GLOBAL_RUNTIME};
use backoff::{future::retry, ExponentialBackoff};
use k8s_openapi::serde::{de::DeserializeOwned, Deserialize, Serialize};
use kube::{
    api::{Api, ApiResource, DynamicObject, GroupVersionKind, PostParams},
    core::{
        gvk::ParseGroupVersionError, ClusterResourceScope, GroupVersion, NamespaceResourceScope,
        Resource,
    },
    Client, ResourceExt,
};
use pyo3::{
    create_exception, exceptions::PyException, prelude::*, types::PyDict, Bound,
};
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

    pub async fn create_or_update_resource<T>(
        &self,
        api: Api<T>,
        resource: T,
    ) -> Result<T, KubeClientError>
    where
        T: Resource + Clone + Debug + DeserializeOwned + Serialize,
    {
        let name = resource.name_any();

        match api.get(&name).await {
            Ok(..) => Ok(retry(ExponentialBackoff::default(), || async {
                let mut new_resource = resource.clone();

                let server_object = api.get(&name).await?;
                new_resource.meta_mut().resource_version = server_object.resource_version();

                match api.replace(&name, &Default::default(), &new_resource).await {
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
            .map_err(KubeClientError::Api)?),
            Err(kube::Error::Api(ref err)) if err.code == 404 => Ok(api
                .create(&PostParams::default(), &resource)
                .await
                .map_err(KubeClientError::Api)?),
            Err(e) => Err(KubeClientError::Api(e))?,
        }
    }

    pub async fn create_or_update_cluster_resource<T>(
        &self,
        resource: T,
    ) -> Result<T, KubeClientError>
    where
        T: Resource<Scope = ClusterResourceScope, DynamicType = ()>
            + Clone
            + Debug
            + DeserializeOwned
            + Serialize,
    {
        let client = self.client.to_owned();
        let api: Api<T> = Api::all(client);

        self.create_or_update_resource(api, resource).await
    }

    pub async fn create_or_update_namespaced_resource<T>(
        &self,
        namespace: &str,
        resource: T,
    ) -> Result<T, KubeClientError>
    where
        T: Resource<Scope = NamespaceResourceScope, DynamicType = ()>
            + Clone
            + std::fmt::Debug
            + for<'de> Deserialize<'de>
            + Serialize,
    {
        let client = self.client.to_owned();
        let api: Api<T> = Api::namespaced(client, namespace);

        self.create_or_update_resource(api, resource).await
    }

    pub async fn delete_resource<T>(&self, api: Api<T>, name: &str) -> Result<(), KubeClientError>
    where
        T: Resource + Clone + std::fmt::Debug + for<'de> Deserialize<'de> + Serialize,
    {
        match api.delete(name, &Default::default()).await {
            Ok(_) => Ok(()),
            Err(kube::Error::Api(ref err)) if err.code == 404 => Ok(()),
            Err(e) => Err(KubeClientError::Api(e)),
        }
    }
}

#[pymethods]
impl KubeClient {
    #[new]
    pub fn new() -> PyResult<Self> {
        let client = crate::kube::new()?;
        Ok(KubeClient { client })
    }

    #[pyo3(signature = (manifest))]
    fn create_or_update(&self, py: Python<'_>, manifest: &Bound<'_, PyDict>) -> PyResult<()> {
        let object: DynamicObject = pythonize::depythonize(manifest)?;

        let types = object.types.to_owned().ok_or(KubeClientError::Metadata)?;

        let gvk = GroupVersionKind::try_from(types).map_err(KubeClientError::ParseGroupVersion)?;
        let api = self.get_api_from_gvk(&gvk, object.metadata.namespace.as_deref());

        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async move {
                self.create_or_update_resource(api, object).await?;

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
            GLOBAL_RUNTIME.block_on(async {
                match retry(ExponentialBackoff::default(), || async {
                    let object = object.clone();
                    let mut remote_object = api.get(&name).await?;

                    remote_object.metadata.labels = object.metadata.labels;
                    remote_object.spec.cluster_network = object.spec.cluster_network;
                    remote_object.spec.topology = object.spec.topology;

                    match api
                        .replace(&name, &Default::default(), &remote_object)
                        .await
                    {
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
        let api = self.get_api_from_gvk(&gvk, namespace);

        py.allow_threads(|| {
            GLOBAL_RUNTIME.block_on(async {
                self.delete_resource(api, name).await?;

                Ok(())
            })
        })
    }
}
