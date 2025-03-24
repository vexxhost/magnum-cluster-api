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

#[cfg(test)]
pub mod fixtures {
    use crate::{
        clients::openstack::{CloudConfig, CloudConfigFile},
        magnum,
    };
    use http::{Request, Response};
    use k8s_openapi::{api::core::v1::Secret, ByteString};
    use kube::{api::ObjectMeta, client::Body, Client, Error};
    use maplit::{btreemap, hashmap};

    type ApiServerHandle = tower_test::mock::Handle<Request<Body>, Response<Body>>;
    pub struct ApiServerVerifier(ApiServerHandle);

    pub enum Scenario {
        GetClusterIdentitySecret(magnum::Cluster, CloudConfig),
        RadioSilence,
    }

    impl ApiServerVerifier {
        pub fn run(self, scenario: Scenario) -> tokio::task::JoinHandle<()> {
            tokio::spawn(async move {
                match scenario {
                    Scenario::GetClusterIdentitySecret(cluster, cloud_config) => {
                        self.handle_get_cluster_identity_secret(&cluster, &cloud_config)
                            .await
                    }
                    Scenario::RadioSilence => Ok(self),
                }
                .expect("scenario completed without errors");
            })
        }

        async fn handle_get_cluster_identity_secret(
            mut self,
            cluster: &magnum::Cluster,
            cloud_config: &CloudConfig,
        ) -> Result<Self, Error> {
            let (request, send) = self.0.next_request().await.expect("service not called");

            let secret_name = cluster
                .cloud_identity_secret_name()
                .expect("failed to get cloud identity secret name");
            let secret_namespace = cluster.namespace();

            assert_eq!(request.method(), http::Method::GET);
            assert_eq!(
                request.uri().to_string(),
                format!(
                    "/api/v1/namespaces/{}/secrets/{}",
                    secret_namespace, secret_name
                )
            );

            let clouds_yaml = CloudConfigFile::builder()
                .clouds(hashmap! {
                    "default".to_owned() => cloud_config.clone(),
                })
                .build();

            let secret = Secret {
                metadata: ObjectMeta {
                    name: Some(secret_name),
                    namespace: Some(secret_namespace.to_string()),
                    ..Default::default()
                },
                data: Some(btreemap! {
                    "clouds.yaml".to_owned() => ByteString(serde_yaml::to_string(&clouds_yaml).expect("failed to serialize clouds.yaml").into_bytes()),
                }),
                ..Default::default()
            };

            send.send_response(
                Response::builder()
                    .body(Body::from(serde_json::to_vec(&secret).unwrap()))
                    .unwrap(),
            );

            Ok(self)
        }
    }

    pub fn get_test_client() -> (Client, ApiServerVerifier) {
        let (mock_service, handle) = tower_test::mock::pair::<Request<Body>, Response<Body>>();
        let client = Client::new(mock_service, "default");

        (client, ApiServerVerifier(handle))
    }
}
