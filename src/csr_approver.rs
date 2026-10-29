//! Integration with cluster-api-csr-approver
//! (<https://github.com/vexxhost/cluster-api-csr-approver>), which approves
//! kubelet serving certificate requests from the management cluster for
//! clusters created with `kubelet_serving_cert_verification_enabled=true`.

use k8s_openapi::api::apps::v1::Deployment;
use kube::{
    api::{Api, ListParams},
    Client,
};
use log::warn;

/// The approver's release manifests put this label on all of their objects,
/// whether they were installed with `clusterctl init --addon` or applied
/// directly.
const PROVIDER_SELECTOR: &str = "cluster.x-k8s.io/provider=addon-csr-approver";

/// Returns whether an approver Deployment is available in the management
/// cluster.
async fn is_available(client: Client) -> Result<bool, kube::Error> {
    let api: Api<Deployment> = Api::all(client);
    let deployments = api
        .list(&ListParams::default().labels(PROVIDER_SELECTOR))
        .await?;

    Ok(deployments.items.iter().any(|deployment| {
        deployment
            .status
            .as_ref()
            .and_then(|status| status.available_replicas)
            .unwrap_or(0)
            > 0
    }))
}

/// Warns the operator when the approver isn't running.
///
/// With `kubelet-certificate-authority` set, kube-apiserver can only reach a
/// kubelet once its serving certificate is approved, and the
/// KubeadmControlPlane etcd health checks go through the kubelet.  Without a
/// running approver, new control plane nodes never become ready.  The Magnum
/// user can't fix that, so the operation goes ahead and the operator gets a
/// log entry explaining why the cluster is stuck.
pub async fn warn_if_unavailable(client: Client, cluster: &str) {
    match is_available(client).await {
        Ok(true) => {}
        Ok(false) => warn!(
            "cluster {cluster} has kubelet_serving_cert_verification_enabled=true, but \
             cluster-api-csr-approver isn't running in the management cluster (no available \
             Deployment labeled {PROVIDER_SELECTOR}), so its nodes won't become ready until it \
             is installed: https://github.com/vexxhost/cluster-api-csr-approver#installing"
        ),
        Err(err) => warn!(
            "cluster {cluster} has kubelet_serving_cert_verification_enabled=true, but checking \
             for cluster-api-csr-approver failed: {err}"
        ),
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

    /// Runs `is_available` against a fake API server that answers the
    /// Deployment list with `items`, and checks the request it received.
    async fn is_available_with(items: Vec<Value>) -> bool {
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

        let result = is_available(client).await.expect("list failed");
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

    #[rstest]
    #[case::available(vec![deployment(json!({"availableReplicas": 1}))], true)]
    #[case::missing(vec![], false)]
    #[case::no_status(vec![deployment(json!({}))], false)]
    #[case::unavailable(vec![deployment(json!({"availableReplicas": 0}))], false)]
    #[tokio::test]
    async fn test_is_available(#[case] items: Vec<Value>, #[case] expected: bool) {
        assert_eq!(is_available_with(items).await, expected);
    }
}
