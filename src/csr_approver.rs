//! Integration with cluster-api-csr-approver
//! (<https://github.com/vexxhost/cluster-api-csr-approver>), which approves
//! kubelet serving certificate requests from the management cluster for
//! clusters created with `kubelet_serving_cert_verification_enabled=true`.

use k8s_openapi::api::apps::v1::Deployment;
use kube::{
    api::{Api, ListParams},
    Client,
};
use thiserror::Error;

/// The approver's release manifests put this label on all of their objects,
/// whether they were installed with `clusterctl init --addon` or applied
/// directly.
const PROVIDER_SELECTOR: &str = "cluster.x-k8s.io/provider=addon-csr-approver";

#[derive(Debug, Error)]
pub enum Error {
    #[error(
        "kubelet_serving_cert_verification_enabled requires cluster-api-csr-approver \
         to be running in the Cluster API management cluster, but no available \
         Deployment labeled {PROVIDER_SELECTOR} was found, see \
         https://github.com/vexxhost/cluster-api-csr-approver#installing"
    )]
    NotAvailable,

    #[error(transparent)]
    Kubernetes(#[from] kube::Error),
}

/// Fails unless the approver is running in the management cluster.
///
/// With `kubelet-certificate-authority` set, kube-apiserver can only reach a
/// kubelet once its serving certificate is approved, and the
/// KubeadmControlPlane etcd health checks go through the kubelet.  Without a
/// running approver, new control plane nodes never become ready, so the
/// driver checks this before it adds nodes to a cluster.
pub async fn ensure_available(client: Client) -> Result<(), Error> {
    let api: Api<Deployment> = Api::all(client);
    let deployments = api
        .list(&ListParams::default().labels(PROVIDER_SELECTOR))
        .await?;

    let available = deployments.items.iter().any(|deployment| {
        deployment
            .status
            .as_ref()
            .and_then(|status| status.available_replicas)
            .unwrap_or(0)
            > 0
    });

    if available {
        Ok(())
    } else {
        Err(Error::NotAvailable)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use http::{Request, Response};
    use kube::client::Body;
    use pretty_assertions::assert_eq;
    use rstest::rstest;
    use serde_json::{json, Value};

    /// Runs `ensure_available` against a fake API server that answers the
    /// Deployment list with `items`, and checks the request it received.
    async fn ensure_available_with(items: Vec<Value>) -> Result<(), Error> {
        let (service, mut handle) = tower_test::mock::pair::<Request<Body>, Response<Body>>();
        let client = Client::new(service, "default");

        let server = tokio::spawn(async move {
            let (request, send) = handle.next_request().await.expect("no request received");

            // A cluster-wide list, filtered to the approver's objects.
            assert_eq!(request.method(), http::Method::GET);
            assert_eq!(request.uri().path(), "/apis/apps/v1/deployments");
            assert!(
                request
                    .uri()
                    .query()
                    .unwrap_or_default()
                    .contains("labelSelector=cluster.x-k8s.io%2Fprovider%3Daddon-csr-approver"),
                "unexpected query: {:?}",
                request.uri().query()
            );

            let body = json!({
                "apiVersion": "apps/v1",
                "kind": "DeploymentList",
                "metadata": {},
                "items": items,
            });
            send.send_response(
                Response::builder()
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            );
        });

        let result = ensure_available(client).await;
        server.await.unwrap();
        result
    }

    fn deployment(status: Value) -> Value {
        json!({
            "metadata": {
                "name": "capi-csr-approver-controller-manager",
                "namespace": "capi-csr-approver-system",
            },
            "status": status,
        })
    }

    #[tokio::test]
    async fn test_ensure_available_with_available_approver() {
        let result = ensure_available_with(vec![deployment(json!({"availableReplicas": 1}))]).await;

        assert!(result.is_ok(), "{:?}", result);
    }

    #[rstest]
    #[case::missing(vec![])]
    #[case::no_status(vec![deployment(json!({}))])]
    #[case::unavailable(vec![deployment(json!({"availableReplicas": 0}))])]
    #[tokio::test]
    async fn test_ensure_available_without_available_approver(#[case] items: Vec<Value>) {
        let result = ensure_available_with(items).await;

        assert!(matches!(result, Err(Error::NotAvailable)), "{:?}", result);
    }
}
