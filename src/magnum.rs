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

/// Default Kubernetes version for clusters
pub const DEFAULT_KUBE_TAG: &str = "v1.30.0";

#[derive(Clone, Default, Deserialize, FromPyObject)]
pub struct ClusterTemplate {
    pub network_driver: String,
}

#[derive(Clone, Default, Deserialize, TypedBuilder)]
pub struct ClusterLabels {
    /// The tag of the Cilium container image to use for the cluster.
    #[builder(default="v1.15.3".to_owned())]
    pub cilium_tag: String,

    /// The IP address range to use for the Cilium IPAM pool.
    #[builder(default="10.100.0.0/16".to_owned())]
    pub cilium_ipv4pool: String,

    /// Enable the use of the Cinder CSI driver for the cluster.
    #[builder(default = true)]
    pub cinder_csi_enabled: bool,

    /// The tag of the Cinder CSI container image to use for the cluster.
    #[builder(default="v1.32.0".to_owned())]
    pub cinder_csi_plugin_tag: String,

    /// Enable the use of the Manila CSI driver for the cluster.
    #[builder(default = true)]
    pub manila_csi_enabled: bool,

    /// The tag of the Manila CSI container image to use for the cluster.
    #[builder(default="v1.32.0".to_owned())]
    pub manila_csi_plugin_tag: String,

    /// The tag to use for the OpenStack cloud controller provider
    /// when bootstrapping the cluster. If not specified, it will be
    /// automatically selected based on the Kubernetes version.
    #[builder(default)]
    pub cloud_provider_tag: Option<String>,

    /// The prefix of the container images to use for the cluster, which
    /// defaults to the upstream images if not set.
    #[builder(default)]
    pub container_infra_prefix: Option<String>,

    /// CSI attacher tag to use for the cluster.
    #[builder(default="v4.7.0".to_owned())]
    pub csi_attacher_tag: String,

    /// CSI liveness probe tag to use for the cluster.
    #[builder(default="v2.14.0".to_owned())]
    pub csi_liveness_probe_tag: String,

    /// CSI Node Driver Registrar tag to use for the cluster.
    #[builder(default="v2.12.0".to_owned())]
    pub csi_node_driver_registrar_tag: String,

    // CSI Provisioner tag to use for the cluster.
    #[builder(default="v5.1.0".to_owned())]
    pub csi_provisioner_tag: String,

    /// CSI Resizer tag to use for the cluster.
    #[builder(default="v1.12.0".to_owned())]
    pub csi_resizer_tag: String,

    /// CSI Snapshotter tag to use for the cluster.
    #[builder(default="v8.1.0".to_owned())]
    pub csi_snapshotter_tag: String,

    /// The Kubernetes version to use for the cluster.
    #[builder(default=DEFAULT_KUBE_TAG.to_owned())]
    pub kube_tag: String,
}

impl<'py> FromPyObject<'py> for ClusterLabels {
    fn extract_bound(ob: &Bound<'py, PyAny>) -> PyResult<Self> {
        let mut labels = ClusterLabels::default();

        if let Ok(val) = ob.get_item("cilium_tag") { labels.cilium_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("cilium_ipv4pool") { labels.cilium_ipv4pool = val.extract()?; }
        if let Ok(val) = ob.get_item("cinder_csi_enabled") { labels.cinder_csi_enabled = val.extract()?; }
        if let Ok(val) = ob.get_item("cinder_csi_plugin_tag") { labels.cinder_csi_plugin_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("manila_csi_enabled") { labels.manila_csi_enabled = val.extract()?; }
        if let Ok(val) = ob.get_item("manila_csi_plugin_tag") { labels.manila_csi_plugin_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("cloud_provider_tag") { labels.cloud_provider_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("container_infra_prefix") { labels.container_infra_prefix = val.extract()?; }
        if let Ok(val) = ob.get_item("csi_attacher_tag") { labels.csi_attacher_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("csi_liveness_probe_tag") { labels.csi_liveness_probe_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("csi_node_driver_registrar_tag") { labels.csi_node_driver_registrar_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("csi_provisioner_tag") { labels.csi_provisioner_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("csi_resizer_tag") { labels.csi_resizer_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("csi_snapshotter_tag") { labels.csi_snapshotter_tag = val.extract()?; }
        if let Ok(val) = ob.get_item("kube_tag") { labels.kube_tag = val.extract()?; }

        Ok(labels)
    }
}

impl ClusterLabels {
    const DEFAULT_CLOUD_PROVIDER_TAG: &'static str = "v1.34.1";

    pub fn get_cloud_provider_tag(&self) -> String {
        if let Some(tag) = &self.cloud_provider_tag {
            return tag.clone();
        }

        let version_str = self.kube_tag.strip_prefix('v').unwrap_or(&self.kube_tag);
        let version = match semver::Version::parse(version_str) {
            Ok(v) => v,
            Err(_) => return Self::DEFAULT_CLOUD_PROVIDER_TAG.to_owned(),
        };

        match (version.major, version.minor) {
            (1, 22) => "v1.22.2".to_owned(),
            (1, 23) => "v1.23.4".to_owned(),
            (1, 24) => "v1.24.6".to_owned(),
            (1, 25) => "v1.25.6".to_owned(),
            (1, 26) => "v1.26.4".to_owned(),
            (1, 27) => "v1.27.3".to_owned(),
            (1, 28) => "v1.28.3".to_owned(),
            (1, 29) => "v1.29.1".to_owned(),
            (1, 30) => "v1.30.3".to_owned(),
            (1, 31) => "v1.31.4".to_owned(),
            (1, 32) => "v1.32.1".to_owned(),
            (1, 33) => "v1.33.1".to_owned(),
            (1, 34) => "v1.34.1".to_owned(),
            _ => Self::DEFAULT_CLOUD_PROVIDER_TAG.to_owned(),
        }
    }
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

#[derive(Clone, Default, Deserialize, FromPyObject)]
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
    pub fn stack_id(&self) -> Result<String, ClusterError> {
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

    pub fn cluster_addon_cluster_resource_set<T: ClusterAddon>(
        &self,
        addon: &T,
    ) -> Result<ClusterResourceSet, ClusterError> {
        Ok(ClusterResourceSet {
            metadata: ObjectMeta {
                name: Some(addon.secret_name()?),
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
                    name: addon.secret_name()?,
                }]),
                strategy: Some(ClusterResourceSetStrategy::Reconcile),
            },
            status: None,
        })
    }

    pub fn cluster_addon_secret<T: ClusterAddon>(&self, addon: &T) -> Result<Secret, ClusterError> {
        Ok(Secret {
            metadata: ObjectMeta {
                name: Some(addon.secret_name()?),
                ..Default::default()
            },
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(addon.manifests()?),
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
            data.insert(
                "cilium.yaml".to_owned(),
                cilium
                    .manifests()
                    .unwrap()
                    .get("cilium.yaml")
                    .unwrap()
                    .to_owned(),
            );
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
    use serde_yaml::{Mapping, Value};
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
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };

        let object_meta: ObjectMeta = cluster.into();

        assert_eq!(object_meta.name, Some("sample-uuid".into()));
    }

    #[test]
    fn test_get_cloud_provider_tag_explicit() {
        let labels = ClusterLabels::builder()
            .cloud_provider_tag(Some("v1.29.5".to_owned()))
            .build();

        assert_eq!(labels.get_cloud_provider_tag(), "v1.29.5");
    }

    #[rstest]
    #[case("v1.22.0", "v1.22.2")]
    #[case("v1.23.0", "v1.23.4")]
    #[case("v1.24.0", "v1.24.6")]
    #[case("v1.25.0", "v1.25.6")]
    #[case("v1.26.0", "v1.26.4")]
    #[case("v1.27.0", "v1.27.3")]
    #[case("v1.28.0", "v1.28.3")]
    #[case("v1.29.0", "v1.29.1")]
    #[case("v1.30.0", "v1.30.3")]
    #[case("v1.31.0", "v1.31.4")]
    #[case("v1.32.0", "v1.32.1")]
    #[case("v1.33.0", "v1.33.1")]
    #[case("v1.34.0", "v1.34.1")]
    #[case("v1.60.1", "v1.34.1")]
    #[case("v2.0.0", "v1.34.1")]
    #[case("invalid", "v1.34.1")]
    #[case("master", "v1.34.1")]
    fn test_get_cloud_provider_tag_from_kube_tag(
        #[case] kube_tag: &str,
        #[case] expected_cloud_provider_tag: &str,
    ) {
        let labels = ClusterLabels::builder()
            .kube_tag(kube_tag.to_owned())
            .build();

        assert_eq!(labels.get_cloud_provider_tag(), expected_cloud_provider_tag);
    }

    #[test]
    fn test_cloud_provider_tag_override() {
        // Test that explicit cloud_provider_tag overrides the automatic selection
        let labels = ClusterLabels::builder()
            .kube_tag("v1.30.0".to_owned())
            .cloud_provider_tag(Some("v1.28.0".to_owned()))
            .build();

        assert_eq!(labels.get_cloud_provider_tag(), "v1.28.0");
    }

    #[test]
    fn test_cluster_stack_id() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };

        let result = cluster.stack_id().expect("failed to get stack id");
        assert_eq!(result, "kube-abcde");
    }

    #[test]
    fn test_cluster_stack_id_missing() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: None,
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
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
    fn test_cluster_addon_cluster_resource_set() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };

        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon
            .expect_secret_name()
            .times(2)
            .returning(|| Ok("kube-abcde-cloud-provider".to_string()));

        let result = cluster
            .cluster_addon_cluster_resource_set(&mock_addon)
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
    fn test_cluster_addon_secret() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };

        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon
            .expect_secret_name()
            .return_once(|| Ok("kube-abcde-cloud-provider".to_string()));
        mock_addon.expect_manifests().return_once(|| {
            Ok(btreemap! {
                "cloud-controller-manager.yaml".to_owned() => "blah".to_owned(),
            })
        });

        let result = cluster
            .cluster_addon_secret(&mock_addon)
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
    fn test_cluster_addon_secret_manifest_render_failure() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };

        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon
            .expect_secret_name()
            .return_once(|| Ok("kube-abcde-cloud-provider".to_string()));
        mock_addon.expect_manifests().return_once(|| {
            Err(helm::HelmTemplateError::HelmCommand(
                "helm template failed".to_string(),
            ))
        });

        let result = cluster.cluster_addon_secret(&mock_addon);

        assert!(result.is_err());
        match result {
            Err(ClusterError::ManifestRender(helm::HelmTemplateError::HelmCommand(e))) => {
                assert_eq!(e, "helm template failed");
            }
            _ => panic!("Expected ClusterError::ManifestRender, got different error"),
        }
    }

    #[test]
    fn test_cluster_addon_resource_set_from_cluster() {
        let cluster = &Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
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
        #[dirs]
        #[exclude("patches")]
        path: PathBuf,
    ) {
        let mut values = Mapping::new();
        let chart_name = path.file_name().unwrap().to_str().unwrap();
        if chart_name == "cilium" {
            let mut cni = Mapping::new();
            cni.insert(
                Value::String("chainingMode".to_string()),
                Value::String("none".to_string()),
            );
            values.insert(Value::String("cni".to_string()), Value::Mapping(cni));
        }
        let docs = helm::template(&path, chart_name, "magnum-system", &values);
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
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };

        let secret: Secret = cluster.clone().into();

        assert_eq!(secret.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            secret.type_,
            Some("addons.cluster.x-k8s.io/resource-set".into())
        );
    }
}
