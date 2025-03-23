use backoff::{future::retry, ExponentialBackoff};
use k8s_openapi::serde::{de::DeserializeOwned, Deserialize, Serialize};
use kube::{
    api::{Api, ApiResource, DynamicObject, GroupVersionKind, PostParams},
    core::{ClusterResourceScope, NamespaceResourceScope, Resource},
    Client, ResourceExt,
};
use pyo3::{exceptions::PyRuntimeError, PyErr};
use std::fmt::Debug;

pub struct Error(kube::Error);

impl From<Error> for PyErr {
    fn from(err: Error) -> Self {
        PyRuntimeError::new_err(err.0.to_string())
    }
}

impl From<kube::Error> for Error {
    fn from(err: kube::Error) -> Self {
        Self(err)
    }
}

pub trait ClientHelpers {
    fn get_api_from_gvk(
        &self,
        gvk: &GroupVersionKind,
        namespace: Option<&str>,
    ) -> Api<DynamicObject>;

    async fn create_or_update_resource<T>(&self, api: Api<T>, resource: T) -> Result<T, Error>
    where
        T: Resource + Clone + Debug + DeserializeOwned + Serialize;

    async fn create_or_update_cluster_resource<T>(&self, resource: T) -> Result<T, Error>
    where
        T: Resource<Scope = ClusterResourceScope, DynamicType = ()>
            + Clone
            + Debug
            + DeserializeOwned
            + Serialize;

    async fn create_or_update_namespaced_resource<T>(
        &self,
        namespace: &str,
        resource: T,
    ) -> Result<T, Error>
    where
        T: Resource<Scope = NamespaceResourceScope, DynamicType = ()>
            + Clone
            + std::fmt::Debug
            + for<'de> Deserialize<'de>
            + Serialize;

    async fn delete_resource<T>(&self, api: Api<T>, name: &str) -> Result<(), Error>
    where
        T: Resource + Clone + std::fmt::Debug + for<'de> Deserialize<'de> + Serialize;
}

impl ClientHelpers for Client {
    fn get_api_from_gvk(
        &self,
        gvk: &GroupVersionKind,
        namespace: Option<&str>,
    ) -> Api<DynamicObject> {
        let api_resource = ApiResource::from_gvk(gvk);

        let api: Api<DynamicObject> = if api_resource.kind == "Namespace" {
            Api::all_with(self.clone(), &api_resource)
        } else {
            Api::namespaced_with(self.clone(), namespace.unwrap(), &api_resource)
        };

        api
    }

    async fn create_or_update_resource<T>(&self, api: Api<T>, resource: T) -> Result<T, Error>
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
            .await?),
            Err(kube::Error::Api(ref err)) if err.code == 404 => {
                Ok(api.create(&PostParams::default(), &resource).await?)
            }
            Err(e) => Err(e)?,
        }
    }

    async fn create_or_update_cluster_resource<T>(&self, resource: T) -> Result<T, Error>
    where
        T: Resource<Scope = ClusterResourceScope, DynamicType = ()>
            + Clone
            + Debug
            + DeserializeOwned
            + Serialize,
    {
        let api: Api<T> = Api::all(self.clone());
        self.create_or_update_resource(api, resource).await
    }

    async fn create_or_update_namespaced_resource<T>(
        &self,
        namespace: &str,
        resource: T,
    ) -> Result<T, Error>
    where
        T: Resource<Scope = NamespaceResourceScope, DynamicType = ()>
            + Clone
            + std::fmt::Debug
            + for<'de> Deserialize<'de>
            + Serialize,
    {
        let api: Api<T> = Api::namespaced(self.clone(), namespace);
        self.create_or_update_resource(api, resource).await
    }

    async fn delete_resource<T>(&self, api: Api<T>, name: &str) -> Result<(), Error>
    where
        T: Resource + Clone + std::fmt::Debug + for<'de> Deserialize<'de> + Serialize,
    {
        match api.delete(name, &Default::default()).await {
            Ok(_) => Ok(()),
            Err(kube::Error::Api(ref err)) if err.code == 404 => Ok(()),
            Err(e) => Err(e)?,
        }
    }
}
