use crate::{
    addons::{cilium, ClusterAddon},
    cluster_api::clusterresourcesets::{
        ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
        ClusterResourceSetResourcesKind, ClusterResourceSetSpec, ClusterResourceSetStrategy,
    },
};
use k8s_openapi::api::core::v1::Secret;
use kube::{
    api::ObjectMeta,
    config::{KubeConfigOptions, Kubeconfig},
    Api, Client, Config,
};
use maplit::btreemap;
use pyo3::{exceptions::PyRuntimeError, prelude::*};
use serde::Deserialize;
use std::collections::BTreeMap;
use thiserror::Error;
use typed_builder::TypedBuilder;

#[derive(Clone, Deserialize, FromPyObject)]
pub struct ClusterTemplate {
    pub network_driver: String,
}

#[derive(Clone, Default, Deserialize, FromPyObject, TypedBuilder)]
#[pyo3(from_item_all)]
pub struct ClusterLabels {
    /// The prefix of the container images to use for the cluster, which
    /// defaults to the upstream images if not set.
    #[builder(default)]
    #[pyo3(default)]
    pub container_infra_prefix: Option<String>,

    /// The tag of the Cilium container image to use for the cluster.
    #[builder(default="v1.15.3".to_owned())]
    #[pyo3(default="v1.15.3".to_owned())]
    pub cilium_tag: String,

    /// The IP address range to use for the Cilium IPAM pool.
    #[builder(default="10.100.0.0/16".to_owned())]
    #[pyo3(default="10.100.0.0/16".to_owned())]
    pub cilium_ipv4pool: String,

    /// The tag to use for the OpenStack cloud controller provider
    /// when bootstrapping the cluster.
    #[builder(default="v1.30.0".to_owned())]
    #[pyo3(default="v1.30.0".to_owned())]
    pub cloud_provider_tag: String,

    /// The Kubernetes version to use for the cluster.
    #[builder(default="v1.30.0".to_owned())]
    pub kube_tag: String,
}

#[derive(Debug, Error)]
pub enum ClusterError {
    #[error("missing stack id for cluster: {0}")]
    MissingStackId(String),

    #[error(transparent)]
    ManifestRender(#[from] helm::HelmTemplateError),

    #[error(transparent)]
    Kubernetes(#[from] kube::Error),

    #[error("kubeconfig secret not found for cluster: {0}")]
    KubeconfigSecretNotFound(String),

    #[error("failed to parse kubeconfig yaml: {0}")]
    KubeconfigParse(#[from] serde_yaml::Error),

    #[error("failed to load kubeconfig: {0}")]
    KubeconfigLoad(#[from] kube::config::KubeconfigError),
}

impl From<ClusterError> for PyErr {
    fn from(err: ClusterError) -> PyErr {
        PyErr::new::<PyRuntimeError, _>(err.to_string())
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Default)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ClusterStatus {
    #[default]
    CreateInProgress,
    CreateFailed,
    CreateComplete,
    UpdateInProgress,
    UpdateFailed,
    UpdateComplete,
    DeleteInProgress,
    DeleteFailed,
    DeleteComplete,
    ResumeComplete,
    ResumeFailed,
    RestoreComplete,
    RollbackInProgress,
    RollbackFailed,
    RollbackComplete,
    SnapshotComplete,
    CheckComplete,
    AdoptComplete,
}

impl FromPyObject<'_> for ClusterStatus {
    fn extract_bound(ob: &Bound<'_, PyAny>) -> PyResult<Self> {
        let status = ob.extract::<String>()?;

        serde_plain::from_str(&status).map_err(|err| {
            PyErr::new::<PyRuntimeError, _>(format!(
                "failed to parse cluster status: {}: {}",
                status, err
            ))
        })
    }
}

#[derive(Default)]
struct ClusterStatus {
    bar: bool
}

#[derive(Clone, Deserialize, FromPyObject)]
pub struct Cluster {
    pub uuid: String,
    pub cluster_template: ClusterTemplate,
    pub stack_id: Option<String>,
    pub labels: ClusterLabels,
    pub status: ClusterStatus,
}

impl From<Cluster> for ObjectMeta {
    fn from(cluster: Cluster) -> Self {
        ObjectMeta {
            name: Some(cluster.uuid),
            ..Default::default()
        }
    }
}

impl Cluster {
    fn stack_id(&self) -> Result<String, ClusterError> {
        self.stack_id
            .clone()
            .ok_or_else(|| ClusterError::MissingStackId(self.uuid.clone()))
    }

    fn kubeconfig_secret_name(&self) -> Result<String, ClusterError> {
        let stack_id = self.stack_id()?;

        Ok(format!("{}-kubeconfig", stack_id))
    }

    async fn kubeconfig(&self) -> Result<Kubeconfig, ClusterError> {
        let client = Client::try_default().await?;
        let api: Api<Secret> = Api::namespaced(client, "magnum-system");
        let secret_name = self.kubeconfig_secret_name()?;

        let secret = api
            .get(&secret_name)
            .await
            .map_err(ClusterError::Kubernetes)?;

        let secret_data = secret
            .data
            .ok_or_else(|| ClusterError::KubeconfigSecretNotFound(secret_name.clone()))?;

        let data = secret_data
            .get("value")
            .ok_or_else(|| ClusterError::KubeconfigSecretNotFound(secret_name.clone()))?;

        serde_yaml::from_slice::<Kubeconfig>(&data.0).map_err(ClusterError::KubeconfigParse)
    }

    pub async fn client(&self) -> Result<Client, ClusterError> {
        let kubeconfig = self.kubeconfig().await?;
        let config =
            Config::from_custom_kubeconfig(kubeconfig, &KubeConfigOptions::default()).await?;
        let client = Client::try_from(config).map_err(ClusterError::Kubernetes)?;

        // TODO: If the Cluster API driver is running outside of the management cluster and this is an
        //       isolated cluster, we need to create a port-forward to the API server through the
        //       management cluster.

        Ok(client)
    }

    pub fn cloud_provider_resource_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-cloud-provider", self.stack_id()?))
    }

    pub fn cloud_provider_cluster_resource_set(&self) -> Result<ClusterResourceSet, ClusterError> {
        let resource_name = self.cloud_provider_resource_name()?;

        Ok(ClusterResourceSet {
            metadata: ObjectMeta {
                name: Some(resource_name.clone()),
                ..Default::default()
            },
            spec: ClusterResourceSetSpec {
                cluster_selector: ClusterResourceSetClusterSelector {
                    match_labels: Some(btreemap! {
                        "cluster-uuid".to_owned() => self.uuid.to_owned(),
                    }),
                    match_expressions: None,
                },
                resources: Some(vec![ClusterResourceSetResources {
                    kind: ClusterResourceSetResourcesKind::Secret,
                    name: resource_name.clone(),
                }]),
                strategy: Some(ClusterResourceSetStrategy::Reconcile),
            },
            status: None,
        })
    }

    pub fn cloud_provider_secret<T: ClusterAddon>(
        &self,
        addon: &T,
    ) -> Result<Secret, ClusterError> {
        Ok(Secret {
            metadata: ObjectMeta {
                name: Some(self.cloud_provider_resource_name()?),
                ..Default::default()
            },
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(btreemap! {
                "cloud-controller-manager.yaml".to_owned() => addon.manifests()?,
            }),
            ..Default::default()
        })
    }
}

impl From<&Cluster> for ClusterResourceSet {
    fn from(cluster: &Cluster) -> Self {
        ClusterResourceSet {
            metadata: cluster.clone().into(),
            spec: ClusterResourceSetSpec {
                cluster_selector: ClusterResourceSetClusterSelector {
                    match_labels: Some(btreemap! {
                        "cluster-uuid".to_owned() => cluster.uuid.to_owned(),
                    }),
                    match_expressions: None,
                },
                resources: Some(vec![ClusterResourceSetResources {
                    kind: ClusterResourceSetResourcesKind::Secret,
                    name: cluster.uuid.to_owned(),
                }]),
                strategy: None,
            },
            status: None,
        }
    }
}

impl From<Cluster> for Secret {
    fn from(cluster: Cluster) -> Self {
        let mut data = BTreeMap::<String, String>::new();

        let cilium = cilium::Addon::new(cluster.clone());
        if cilium.enabled() {
            data.insert("cilium.yaml".to_owned(), cilium.manifests().unwrap());
        }

        Secret {
            metadata: cluster.clone().into(),
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(data),
            ..Default::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::addons;
    use pretty_assertions::assert_eq;
    use pyo3::{prepare_freethreaded_python, types::PyString};
    use rstest::rstest;
    use serde::Serialize;
    use serde_yaml::Value;
    use std::path::PathBuf;

    const CLUSTER_SCOPED_RESOURCES: &[&str] = &[
        "APIServer",
        "CSIDriver",
        "ClusterRole",
        "ClusterRoleBinding",
        "Installation",
        "StorageClass",
    ];

    #[rstest]
    #[case("CREATE_IN_PROGRESS", ClusterStatus::CreateInProgress)]
    #[case("CREATE_FAILED", ClusterStatus::CreateFailed)]
    fn test_cluster_status_from_pyobject(#[case] status: &str, #[case] expected: ClusterStatus) {
        prepare_freethreaded_python();

        Python::with_gil(|py| {
            let py_status = PyString::new(py, status);
            let result: ClusterStatus = py_status
                .extract()
                .expect("Failed to extract ClusterStatus");
            assert_eq!(result, expected);
        });
    }

    #[test]
    fn test_cluster_status_from_pyobject_invalid() {
        prepare_freethreaded_python();

        Python::with_gil(|py| {
            let py_status = PyString::new(py, "INVALID_STATUS");
            let result: Result<ClusterStatus, _> = py_status.extract();
            assert!(result.is_err());
        });
    }

    #[test]
    fn test_object_meta_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let object_meta: ObjectMeta = cluster.into();

        assert_eq!(object_meta.name, Some("sample-uuid".into()));
    }

    #[test]
    fn test_cluster_stack_id() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster.stack_id().expect("failed to get stack id");
        assert_eq!(result, "kube-abcde");
    }

    #[test]
    fn test_cluster_stack_id_missing() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::builder().build(),
            stack_id: None,
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster
            .stack_id()
            .expect_err("expected missing stack id error");

        match result {
            ClusterError::MissingStackId(uuid) => {
                assert_eq!(uuid, "sample-uuid");
            }
            _ => panic!("Expected ClusterError::MissingStackId, got different error"),
        }
    }

    #[test]
    fn test_cluster_cloud_provider_resource_name() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster
            .cloud_provider_resource_name()
            .expect("failed to get resource name");
        assert_eq!(result, "kube-abcde-cloud-provider");
    }

    #[test]
    fn test_cluster_cloud_provider_cluster_resource_set() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster
            .cloud_provider_cluster_resource_set()
            .expect("failed to generate crs");

        let expected_resource_name = format!("kube-abcde-cloud-provider");
        let expected = ClusterResourceSet {
            metadata: ObjectMeta {
                name: Some(expected_resource_name.clone()),
                ..Default::default()
            },
            spec: ClusterResourceSetSpec {
                cluster_selector: ClusterResourceSetClusterSelector {
                    match_labels: Some(btreemap! {
                        "cluster-uuid".to_owned() => cluster.uuid,
                    }),
                    match_expressions: None,
                },
                resources: Some(vec![ClusterResourceSetResources {
                    kind: ClusterResourceSetResourcesKind::Secret,
                    name: expected_resource_name.clone(),
                }]),
                strategy: Some(ClusterResourceSetStrategy::Reconcile),
            },
            status: None,
        };

        assert_eq!(expected, result);
    }

    #[test]
    fn test_cluster_cloud_provider_secret() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::builder().build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon
            .expect_manifests()
            .return_once(|| Ok("blah".to_string()));

        let result = cluster
            .cloud_provider_secret(&mock_addon)
            .expect("failed to generate secret");

        let expected = Secret {
            metadata: ObjectMeta {
                name: Some("kube-abcde-cloud-provider".into()),
                ..Default::default()
            },
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(btreemap! {
                "cloud-controller-manager.yaml".to_owned() => "blah".to_owned(),
            }),
            ..Default::default()
        };

        assert_eq!(expected, result);
    }

    #[test]
    fn test_cluster_cloud_provider_secret_manifest_render_failure() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::builder().build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };
        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon.expect_manifests().return_once(|| {
            Err(helm::HelmTemplateError::HelmCommand(
                "helm template failed".to_string(),
            ))
        });

        let result = cluster.cloud_provider_secret(&mock_addon);

        assert!(result.is_err());
        match result {
            Err(ClusterError::ManifestRender(helm::HelmTemplateError::HelmCommand(e))) => {
                assert_eq!(e, "helm template failed");
            }
            _ => panic!("Expected ClusterError::ManifestRender, got different error"),
        }
    }

    #[test]
    fn test_cluster_resource_set_from_cluster() {
        let cluster = &Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let crs: ClusterResourceSet = cluster.into();

        assert_eq!(crs.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            crs.spec.cluster_selector.match_labels,
            Some(btreemap! {
                "cluster-uuid".to_owned() => cluster.uuid.clone(),
            }),
        );

        assert_eq!(
            crs.spec.resources,
            Some(vec![ClusterResourceSetResources {
                kind: ClusterResourceSetResourcesKind::Secret,
                name: cluster.uuid.clone(),
            }])
        );
    }

    #[rstest]
    fn test_helm_charts_render_with_namespace(
        #[files("magnum_cluster_api/charts/*")]
        #[exclude("patches")]
        path: PathBuf,
    ) {
        #[derive(Serialize)]
        struct Values {}
        let values = Values {};

        let docs = helm::template(
            &path,
            path.file_name().unwrap().to_str().unwrap(),
            "magnum-system",
            &values,
        );
        assert!(
            docs.is_ok(),
            "failed to render chart: {}",
            docs.unwrap_err()
        );

        let docs = docs.unwrap();
        let docs: Vec<serde_yaml::Value> = serde_yaml::Deserializer::from_str(&docs)
            .map(serde_yaml::Value::deserialize)
            .collect::<Result<_, _>>()
            .expect("failed to parse rendered documents");

        for doc in docs {
            if CLUSTER_SCOPED_RESOURCES.contains(&doc.get("kind").unwrap().as_str().unwrap()) {
                continue;
            }

            let metadata = doc
                .get("metadata")
                .and_then(|v| v.as_mapping())
                .expect("expected metadata mapping for non-cluster-scoped resource");
            let ns = metadata
                .get(&Value::String("namespace".into()))
                .expect(&format!(
                    "expected namespace field in metadata in document: {:?}",
                    doc
                ));

            assert_eq!(
                ns,
                &Value::String("magnum-system".into()),
                "namespace is not correctly set in document: {:?}",
                doc
            );
        }
    }

    #[test]
    fn test_secret_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            status: ClusterStatus::CreateInProgress,
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let secret: Secret = cluster.clone().into();

        assert_eq!(secret.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            secret.type_,
            Some("addons.cluster.x-k8s.io/resource-set".into())
        );
    }
}
