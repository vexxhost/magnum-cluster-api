use crate::{
    addons::{cilium, ClusterAddon},
    cluster_api::clusterresourcesets::{
        ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
        ClusterResourceSetResourcesKind, ClusterResourceSetSpec, ClusterResourceSetStrategy,
    },
};
use k8s_openapi::api::core::v1::Secret;
use kube::api::ObjectMeta;
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
    /// The tag of the Cilium container image to use for the cluster.
    #[builder(default="v1.15.3".to_owned())]
    #[pyo3(default="v1.15.3".to_owned())]
    pub cilium_tag: String,

    /// The IP address range to use for the Cilium IPAM pool.
    #[builder(default="10.100.0.0/16".to_owned())]
    #[pyo3(default="10.100.0.0/16".to_owned())]
    pub cilium_ipv4pool: String,

    /// Enable the use of the Cinder CSI driver for the cluster.
    #[builder(default = true)]
    #[pyo3(default = true)]
    pub cinder_csi_enabled: bool,

    /// The tag of the Cinder CSI container image to use for the cluster.
    #[builder(default="v1.32.0".to_owned())]
    #[pyo3(default="v1.32.0".to_owned())]
    pub cinder_csi_plugin_tag: String,

    /// Enable the use of the Manila CSI driver for the cluster.
    #[builder(default = true)]
    #[pyo3(default = true)]
    pub manila_csi_enabled: bool,

    /// The tag of the Manila CSI container image to use for the cluster.
    #[builder(default="v1.32.0".to_owned())]
    #[pyo3(default="v1.32.0".to_owned())]
    pub manila_csi_plugin_tag: String,

    /// The tag to use for the OpenStack cloud controller provider
    /// when bootstrapping the cluster.
    #[builder(default="v1.30.0".to_owned())]
    #[pyo3(default="v1.30.0".to_owned())]
    pub cloud_provider_tag: String,

    /// The prefix of the container images to use for the cluster, which
    /// defaults to the upstream images if not set.
    #[builder(default)]
    #[pyo3(default)]
    pub container_infra_prefix: Option<String>,

    /// CSI attacher tag to use for the cluster.
    #[builder(default="v4.7.0".to_owned())]
    #[pyo3(default="v4.7.0".to_owned())]
    pub csi_attacher_tag: String,

    /// CSI liveness probe tag to use for the cluster.
    #[builder(default="v2.14.0".to_owned())]
    #[pyo3(default="v2.14.0".to_owned())]
    pub csi_liveness_probe_tag: String,

    /// CSI Node Driver Registrar tag to use for the cluster.
    #[builder(default="v2.12.0".to_owned())]
    #[pyo3(default="v2.12.0".to_owned())]
    pub csi_node_driver_registrar_tag: String,

    // CSI Provisioner tag to use for the cluster.
    #[builder(default="v5.1.0".to_owned())]
    #[pyo3(default="v5.1.0".to_owned())]
    pub csi_provisioner_tag: String,

    /// CSI Resizer tag to use for the cluster.
    #[builder(default="v1.12.0".to_owned())]
    #[pyo3(default="v1.12.0".to_owned())]
    pub csi_resizer_tag: String,

    /// CSI Snapshotter tag to use for the cluster.
    #[builder(default="v8.1.0".to_owned())]
    #[pyo3(default="v8.1.0".to_owned())]
    pub csi_snapshotter_tag: String,

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
}

impl From<ClusterError> for PyErr {
    fn from(err: ClusterError) -> PyErr {
        PyErr::new::<PyRuntimeError, _>(err.to_string())
    }
}

#[derive(Clone, Deserialize, FromPyObject)]
pub struct Cluster {
    pub uuid: String,
    pub cluster_template: ClusterTemplate,
    pub stack_id: Option<String>,
    pub labels: ClusterLabels,
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

    #[test]
    fn test_object_meta_from_cluster() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
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
    fn test_cluster_addon_cluster_resource_set() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
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
        };

        let secret: Secret = cluster.clone().into();

        assert_eq!(secret.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            secret.type_,
            Some("addons.cluster.x-k8s.io/resource-set".into())
        );
    }
}
