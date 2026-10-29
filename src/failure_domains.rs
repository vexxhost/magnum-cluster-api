//! Clear empty `failureDomain` values left behind by older releases.
//!
//! Older magnum-cluster-api releases set `failureDomain: ""` on worker
//! machine deployments without an availability zone, and Cluster API copied
//! it into MachineDeployments, MachineSets and Machines. Cluster API v1.10
//! made that value invalid (it must be unset or non-empty).
//!
//! On management clusters running Kubernetes older than 1.30 (no CRD
//! validation ratcheting), every update to an object still holding `""` is
//! rejected, including unrelated ones such as Cluster API scaling a
//! MachineSet or the autoscaler marking a Machine for deletion. Newer API
//! servers accept updates that leave the stored value untouched, but still
//! reject any new object derived from it, such as the MachineSet created
//! during a rollout. Either way the value has to go, and because validation
//! covers the whole object, every `""` in an object must be removed in the
//! same request.
//!
//! The objects of a cluster are cleared in this order:
//!
//! 1. MachineSets, so their templates already match the MachineDeployment
//!    templates once those lose the field; otherwise each MachineDeployment
//!    would roll out new Machines.
//! 2. MachineDeployments, so they match what the topology controller renders
//!    once the Cluster loses the field.
//! 3. Machines, which are not templates and never trigger a rollout.
//! 4. The Cluster topology, all machine deployments in one patch.
//!
//! Each patch is a JSON Patch that `test`s for `""` before it `remove`s the
//! field, so a value changed concurrently is never dropped. The patches must
//! not be built by editing and re-sending the whole object: pykube's
//! `update()` merges removed keys back in from the original object, which is
//! why the previous Python implementation never removed anything.

use json_patch::Patch as JsonPatch;
use kube::{
    api::{Api, ApiResource, DynamicObject, GroupVersionKind, ListParams, Patch, PatchParams},
    Client, ResourceExt,
};
use serde_json::{json, Value};

const TEMPLATE_FAILURE_DOMAIN: &str = "/spec/template/spec/failureDomain";
const MACHINE_FAILURE_DOMAIN: &str = "/spec/failureDomain";
const MACHINE_DEPLOYMENTS: &str = "/spec/topology/workers/machineDeployments";

/// Cluster API kinds that carry a `failureDomain`, in the order they must be
/// cleared, with the location of the field.
const KINDS: [(&str, &str); 3] = [
    ("MachineSet", TEMPLATE_FAILURE_DOMAIN),
    ("MachineDeployment", TEMPLATE_FAILURE_DOMAIN),
    ("Machine", MACHINE_FAILURE_DOMAIN),
];

fn cluster_api(client: &Client, namespace: &str, kind: &str) -> Api<DynamicObject> {
    let resource =
        ApiResource::from_gvk(&GroupVersionKind::gvk("cluster.x-k8s.io", "v1beta1", kind));
    Api::namespaced_with(client.clone(), namespace, &resource)
}

fn remove_if_empty(path: &str) -> [Value; 2] {
    [
        json!({"op": "test", "path": path, "value": ""}),
        json!({"op": "remove", "path": path}),
    ]
}

fn into_patch(operations: Vec<Value>) -> JsonPatch {
    serde_json::from_value(Value::Array(operations)).expect("valid JSON patch operations")
}

/// Patch removing an empty `failureDomain` at `pointer` from an object.
pub fn object_patch(object: &Value, pointer: &str) -> Option<JsonPatch> {
    (object.pointer(pointer)? == "").then(|| into_patch(remove_if_empty(pointer).to_vec()))
}

/// Patch removing every empty `failureDomain` from the machine deployments of a
/// Cluster topology. Each list index is guarded by a `test` on the entry's
/// name, so the patch fails instead of editing another entry if the list
/// changed in the meantime.
pub fn cluster_patch(cluster: &Value) -> Option<JsonPatch> {
    let operations: Vec<Value> = cluster
        .pointer(MACHINE_DEPLOYMENTS)?
        .as_array()?
        .iter()
        .enumerate()
        .filter(|(_, md)| md.get("failureDomain").is_some_and(|fd| fd == ""))
        .flat_map(|(index, md)| {
            let entry = format!("{MACHINE_DEPLOYMENTS}/{index}");
            let mut ops =
                vec![json!({"op": "test", "path": format!("{entry}/name"), "value": md["name"]})];
            ops.extend(remove_if_empty(&format!("{entry}/failureDomain")));
            ops
        })
        .collect();

    (!operations.is_empty()).then(|| into_patch(operations))
}

/// Remove empty `failureDomain` values from all Cluster API objects of a
/// cluster, in the order described in the module documentation.
pub async fn clear_empty_failure_domains(
    client: &Client,
    namespace: &str,
    cluster_name: &str,
) -> Result<(), kube::Error> {
    let params = PatchParams::default();
    let selector = format!("cluster.x-k8s.io/cluster-name={cluster_name}");

    for (kind, pointer) in KINDS {
        let api = cluster_api(client, namespace, kind);
        for object in api.list(&ListParams::default().labels(&selector)).await? {
            let value = serde_json::to_value(&object).map_err(kube::Error::SerdeError)?;
            if let Some(patch) = object_patch(&value, pointer) {
                api.patch(&object.name_any(), &params, &Patch::Json::<()>(patch))
                    .await?;
            }
        }
    }

    let clusters = cluster_api(client, namespace, "Cluster");
    if let Some(cluster) = clusters.get_opt(cluster_name).await? {
        let value = serde_json::to_value(&cluster).map_err(kube::Error::SerdeError)?;
        if let Some(patch) = cluster_patch(&value) {
            clusters
                .patch(cluster_name, &params, &Patch::Json::<()>(patch))
                .await?;
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ops(patch: Option<JsonPatch>) -> Value {
        serde_json::to_value(patch.expect("expected a patch")).unwrap()
    }

    mod object_patch {
        use super::*;
        use pretty_assertions::assert_eq;

        #[test]
        fn removes_empty_template_value() {
            let machine_set = json!({"spec": {"template": {"spec": {"failureDomain": ""}}}});

            assert_eq!(
                ops(object_patch(&machine_set, TEMPLATE_FAILURE_DOMAIN)),
                json!([
                    {"op": "test", "path": "/spec/template/spec/failureDomain", "value": ""},
                    {"op": "remove", "path": "/spec/template/spec/failureDomain"},
                ])
            );
        }

        #[test]
        fn removes_empty_machine_value() {
            let machine = json!({"spec": {"failureDomain": ""}});

            assert_eq!(
                ops(object_patch(&machine, MACHINE_FAILURE_DOMAIN)),
                json!([
                    {"op": "test", "path": "/spec/failureDomain", "value": ""},
                    {"op": "remove", "path": "/spec/failureDomain"},
                ])
            );
        }

        #[test]
        fn keeps_real_failure_domain() {
            let machine = json!({"spec": {"failureDomain": "nova"}});

            assert!(object_patch(&machine, MACHINE_FAILURE_DOMAIN).is_none());
        }

        #[test]
        fn skips_unset_failure_domain() {
            let machine_set = json!({"spec": {"template": {"spec": {}}}});

            assert!(object_patch(&machine_set, TEMPLATE_FAILURE_DOMAIN).is_none());
        }
    }

    mod cluster_patch {
        use super::*;
        use pretty_assertions::assert_eq;

        fn cluster(machine_deployments: Value) -> Value {
            json!({"spec": {"topology": {"workers": {"machineDeployments": machine_deployments}}}})
        }

        #[test]
        fn removes_every_empty_value_in_one_patch() {
            let cluster = cluster(json!([
                {"name": "default-worker", "failureDomain": ""},
                {"name": "placed-worker", "failureDomain": "nova"},
                {"name": "unset-worker"},
                {"name": "other-worker", "failureDomain": ""},
            ]));

            assert_eq!(
                ops(cluster_patch(&cluster)),
                json!([
                    {"op": "test", "path": "/spec/topology/workers/machineDeployments/0/name", "value": "default-worker"},
                    {"op": "test", "path": "/spec/topology/workers/machineDeployments/0/failureDomain", "value": ""},
                    {"op": "remove", "path": "/spec/topology/workers/machineDeployments/0/failureDomain"},
                    {"op": "test", "path": "/spec/topology/workers/machineDeployments/3/name", "value": "other-worker"},
                    {"op": "test", "path": "/spec/topology/workers/machineDeployments/3/failureDomain", "value": ""},
                    {"op": "remove", "path": "/spec/topology/workers/machineDeployments/3/failureDomain"},
                ])
            );
        }

        #[test]
        fn skips_cluster_without_empty_values() {
            let cluster = cluster(json!([
                {"name": "placed-worker", "failureDomain": "nova"},
                {"name": "unset-worker"},
            ]));

            assert!(cluster_patch(&cluster).is_none());
        }

        #[test]
        fn skips_cluster_without_topology() {
            assert!(cluster_patch(&json!({"spec": {}})).is_none());
        }
    }

    mod clear_empty_failure_domains {
        use super::*;
        use http::{Method, Request, Response};
        use kube::client::Body;
        use pretty_assertions::assert_eq;
        use tower_test::mock::{Handle, SendResponse};

        type ApiServer = Handle<Request<Body>, Response<Body>>;

        const PREFIX: &str = "/apis/cluster.x-k8s.io/v1beta1/namespaces/magnum-system";
        const SELECTOR: &str = "&labelSelector=cluster.x-k8s.io%2Fcluster-name%3Dkube-abcde";

        fn object(kind: &str, name: &str, spec: Value) -> Value {
            json!({
                "apiVersion": "cluster.x-k8s.io/v1beta1",
                "kind": kind,
                "metadata": {"name": name, "namespace": "magnum-system"},
                "spec": spec,
            })
        }

        fn respond(send: SendResponse<Response<Body>>, body: Value) {
            send.send_response(
                Response::builder()
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            );
        }

        async fn expect_list(api_server: &mut ApiServer, plural: &str, items: Vec<Value>) {
            let (request, send) = api_server.next_request().await.expect("expected a LIST");
            assert_eq!(request.method(), Method::GET);
            assert_eq!(request.uri().path(), format!("{PREFIX}/{plural}"));
            assert_eq!(request.uri().query(), Some(SELECTOR));
            respond(
                send,
                json!({"apiVersion": "cluster.x-k8s.io/v1beta1", "kind": "List", "metadata": {}, "items": items}),
            );
        }

        /// Expect a JSON Patch to `path`, answer it and return its operations.
        async fn expect_json_patch(api_server: &mut ApiServer, path: &str) -> Value {
            let (request, send) = api_server.next_request().await.expect("expected a PATCH");
            assert_eq!(request.method(), Method::PATCH);
            assert_eq!(request.uri().path(), path);
            assert_eq!(
                request.headers()["content-type"],
                "application/json-patch+json"
            );
            let body = request.into_body().collect_bytes().await.unwrap();
            respond(send, object("Cluster", "patched", json!({})));

            serde_json::from_slice(&body).unwrap()
        }

        #[tokio::test]
        async fn clears_machine_sets_deployments_machines_then_cluster() {
            let (service, mut api_server) =
                tower_test::mock::pair::<Request<Body>, Response<Body>>();
            let client = Client::new(service, "magnum-system");

            let server = tokio::spawn(async move {
                let template = |fd: &str| json!({"template": {"spec": {"failureDomain": fd}}});

                expect_list(
                    &mut api_server,
                    "machinesets",
                    vec![
                        object("MachineSet", "stale", template("")),
                        object("MachineSet", "placed", template("nova")),
                    ],
                )
                .await;
                let patch =
                    expect_json_patch(&mut api_server, &format!("{PREFIX}/machinesets/stale"))
                        .await;
                assert_eq!(
                    patch[1],
                    json!({"op": "remove", "path": TEMPLATE_FAILURE_DOMAIN})
                );

                expect_list(
                    &mut api_server,
                    "machinedeployments",
                    vec![object("MachineDeployment", "stale", template(""))],
                )
                .await;
                let patch = expect_json_patch(
                    &mut api_server,
                    &format!("{PREFIX}/machinedeployments/stale"),
                )
                .await;
                assert_eq!(
                    patch[1],
                    json!({"op": "remove", "path": TEMPLATE_FAILURE_DOMAIN})
                );

                expect_list(
                    &mut api_server,
                    "machines",
                    vec![object("Machine", "stale", json!({"failureDomain": ""}))],
                )
                .await;
                let patch =
                    expect_json_patch(&mut api_server, &format!("{PREFIX}/machines/stale")).await;
                assert_eq!(
                    patch[1],
                    json!({"op": "remove", "path": MACHINE_FAILURE_DOMAIN})
                );

                let (request, send) = api_server.next_request().await.expect("expected a GET");
                assert_eq!(request.method(), Method::GET);
                assert_eq!(
                    request.uri().path(),
                    format!("{PREFIX}/clusters/kube-abcde")
                );
                respond(
                    send,
                    object(
                        "Cluster",
                        "kube-abcde",
                        json!({"topology": {"workers": {"machineDeployments": [
                            {"name": "default-worker", "failureDomain": ""},
                            {"name": "other-worker", "failureDomain": ""},
                        ]}}}),
                    ),
                );
                let patch =
                    expect_json_patch(&mut api_server, &format!("{PREFIX}/clusters/kube-abcde"))
                        .await;
                assert_eq!(patch.as_array().unwrap().len(), 6);
            });

            clear_empty_failure_domains(&client, "magnum-system", "kube-abcde")
                .await
                .expect("clearing failure domains failed");
            server.await.expect("API server expectations failed");
        }
    }
}
