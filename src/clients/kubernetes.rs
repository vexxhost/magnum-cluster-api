use backon::{ExponentialBuilder, Retryable};
use k8s_openapi::serde::{de::DeserializeOwned, Deserialize, Serialize};
use kube::{
    api::{Api, ApiResource, DynamicObject, GroupVersionKind, ListParams, PostParams},
    core::{ClusterResourceScope, NamespaceResourceScope, Resource},
    Client, ResourceExt,
};
use pyo3::{exceptions::PyRuntimeError, PyErr};
use pyo3_async_runtimes::tokio::get_runtime;
use std::fmt::Debug;
use tokio::sync::OnceCell;

/// Process-wide cache for the shared `kube::Client`.
///
/// Every `kube::Client` constructed via `Client::try_default()` owns its own
/// `hyper_util` connection pool. The pool spawns background tokio tasks that
/// hold onto sockets (and transitively eventfd/eventpoll file descriptors),
/// and those tasks are not joined/aborted when the client is dropped — see
/// <https://github.com/tokio-rs/tokio/issues/1830>. In a long-running
/// process like `magnum-conductor`, where `Monitor::poll_health_status` is
/// invoked continuously for every cluster, that leak eventually exhausts the
/// open-file limit and surfaces as "Too many open files"
/// (<https://github.com/vexxhost/magnum-cluster-api/issues/822>).
///
/// The fix is to build the client exactly once per process and reuse clones
/// of it at every call site. `kube::Client` is cheap to clone (its inner
/// service is `Arc`-wrapped), so sharing a single instance is safe and
/// efficient.
///
/// We use [`tokio::sync::OnceCell`] so that the *same* cell can be initialised
/// from either a synchronous context (pyo3 entry points that call
/// `shared_client()`) or an asynchronous one (`shared_client_async()`), and in
/// both cases exactly one `Client::try_default()` call is ever made regardless
/// of how many threads/tasks race on first use. This closes the
/// check-then-init gap and eliminates the "loser builds and drops a client"
/// regression that would otherwise leak a few FDs on startup.
static SHARED_CLIENT: OnceCell<Client> = OnceCell::const_new();

/// Async accessor for the process-wide shared `kube::Client`.
///
/// Safe to call from inside a running tokio runtime (e.g. from `async fn`s
/// that are driven by `get_runtime().block_on(...)`), where the sync variant
/// would panic on a nested `block_on`.
pub async fn shared_client_async() -> Result<Client, Error> {
    SHARED_CLIENT
        .get_or_try_init(|| async { Client::try_default().await.map_err(Error) })
        .await
        .cloned()
}

/// Blocking accessor for the process-wide shared `kube::Client`.
///
/// Intended for pyo3 constructors (`Monitor::new`, `Driver::new`,
/// `KubeClient::new`) which are called synchronously from Python and must
/// return an already-built `Client`. Internally driven on the tokio runtime
/// shared with `pyo3_async_runtimes`, so only a single `Client` is ever
/// constructed even if sync and async callers race.
pub fn shared_client() -> Result<Client, Error> {
    get_runtime().block_on(shared_client_async())
}

#[derive(Debug)]
pub struct Error(kube::Error);

impl Error {
    /// Consumes the wrapper and returns the underlying [`kube::Error`].
    pub fn into_inner(self) -> kube::Error {
        self.0
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        std::fmt::Display::fmt(&self.0, f)
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.0)
    }
}

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

    async fn delete_resources<T>(&self, api: Api<T>, list_params: &ListParams) -> Result<(), Error>
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
            Ok(..) => Ok((|| async {
                let mut new_resource = resource.clone();

                let server_object = api.get(&name).await?;
                new_resource.meta_mut().resource_version = server_object.resource_version();

                api.replace(&name, &Default::default(), &new_resource).await
            })
            .retry(ExponentialBuilder::default())
            .when(|e| matches!(e, kube::Error::Api(api_err) if api_err.code == 409))
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

    async fn delete_resources<T>(&self, api: Api<T>, list_params: &ListParams) -> Result<(), Error>
    where
        T: Resource + Clone + std::fmt::Debug + for<'de> Deserialize<'de> + Serialize,
    {
        let list = api.list(list_params).await?;

        for item in list.items {
            self.delete_resource(api.clone(), &item.name_any()).await?;
        }

        Ok(())
    }
}

#[cfg(test)]
#[allow(dead_code)]
pub mod fixtures {
    use http::{Request, Response};
    use kube::{client::Body, Client, Error};

    type ApiServerHandle = tower_test::mock::Handle<Request<Body>, Response<Body>>;
    pub struct ApiServerVerifier(ApiServerHandle);

    pub enum Scenario {
        RadioSilence,
    }

    impl ApiServerVerifier {
        pub fn run(self, scenario: Scenario) -> tokio::task::JoinHandle<()> {
            tokio::spawn(async move {
                match scenario {
                    Scenario::RadioSilence => Ok::<ApiServerVerifier, Error>(self),
                }
                .expect("scenario completed without errors");
            })
        }
    }

    pub fn get_test_client() -> (Client, ApiServerVerifier) {
        let (mock_service, handle) = tower_test::mock::pair::<Request<Body>, Response<Body>>();
        let client = Client::new(mock_service, "default");

        (client, ApiServerVerifier(handle))
    }
}
