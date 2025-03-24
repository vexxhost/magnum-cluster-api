use crate::{
    addons::{cilium, ClusterAddon},
    clients::openstack::{CloudConfig, CloudConfigFile},
    cluster_api::clusterresourcesets::{
        ClusterResourceSet, ClusterResourceSetClusterSelector, ClusterResourceSetResources,
        ClusterResourceSetResourcesKind, ClusterResourceSetSpec, ClusterResourceSetStrategy,
    },
};
use ini::Ini;
use k8s_openapi::api::core::v1::Secret;
use kube::{api::ObjectMeta, Api, Client};
use maplit::{btreemap, hashmap};
use openstack_sdk::{
    api::RestClient,
    config::ConfigFile,
    types::{ApiVersion, ServiceType},
    AsyncOpenStack,
};
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

    /// Octavia provider version to use for the cluster.
    #[builder(default="amphora".to_owned())]
    #[pyo3(default="amphora".to_owned())]
    pub octavia_provider: String,

    /// Load balancer algorithm to use for the Octavia load balancer.
    #[builder(default)]
    #[pyo3(default)]
    pub octavia_lb_algorithm: Option<String>,

    /// Enable or disable the Octavia load balancer health check.
    #[builder(default = true)]
    #[pyo3(default = true)]
    pub octavia_lb_healthcheck: bool,
}

#[derive(Clone, Deserialize, FromPyObject)]
pub struct Cluster {
    pub uuid: String,
    pub cluster_template: ClusterTemplate,
    pub stack_id: Option<String>,
    pub labels: ClusterLabels,
}

#[derive(Debug, Error)]
pub enum ClusterError {
    #[error("missing stack id for cluster: {0}")]
    MissingStackId(String),

    #[error(transparent)]
    ManifestRender(#[from] helm::HelmTemplateError),

    #[error(transparent)]
    Serialization(#[from] serde_yaml::Error),

    #[error(transparent)]
    Kubernetes(#[from] kube::Error),

    #[error(transparent)]
    Io(#[from] std::io::Error),

    #[error(transparent)]
    OpenStack(#[from] openstack_sdk::OpenStackError),

    #[error(transparent)]
    OpenStackApiError(#[from] openstack_sdk::api::ApiError<openstack_sdk::RestError>),

    #[error("invalid octavia load balancer provider: {0}")]
    InvalidOctaviaLoadBalancerProvider(String),

    #[error("invalid octavia load balancer algorithm: {0}")]
    InvalidOctaviaLoadBalancerAlgorithm(String),
}

impl From<ClusterError> for PyErr {
    fn from(err: ClusterError) -> PyErr {
        PyErr::new::<PyRuntimeError, _>(err.to_string())
    }
}

impl From<&Cluster> for ObjectMeta {
    fn from(cluster: &Cluster) -> Self {
        ObjectMeta {
            name: Some(cluster.uuid.clone()),
            ..Default::default()
        }
    }
}

impl Cluster {
    pub fn namespace(&self) -> &str {
        "magnum-system"
    }

    pub fn cloud_identity_secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-cloud-config", self.stack_id()?))
    }

    fn stack_id(&self) -> Result<String, ClusterError> {
        self.stack_id
            .clone()
            .ok_or_else(|| ClusterError::MissingStackId(self.uuid.clone()))
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

    async fn openstack_session(
        &self,
        cloud_config: &CloudConfig,
    ) -> Result<AsyncOpenStack, ClusterError> {
        // NOTE(mnaser): This is a workaround because the current Rust client
        //               doesn't support creating a client directly using a
        //               CloudConfig object.  This will be removed once the
        //               following is addressed:
        //
        //               - https://github.com/gtema/openstack/issues/1082
        let clouds_file = tempfile::Builder::new().suffix(".yaml").tempfile()?;
        serde_yaml::to_writer(
            &clouds_file,
            &CloudConfigFile {
                clouds: hashmap! {
                    "default".to_owned() => cloud_config.clone(),
                },
            },
        )?;

        let cfg = ConfigFile::builder()
            .add_source(clouds_file.path())
            .expect("failed to add openstack config source")
            .build();

        let config = cfg.get_cloud_config("default").unwrap().unwrap();
        AsyncOpenStack::new(&config)
            .await
            .map_err(ClusterError::OpenStack)
    }

    async fn cloud_config_ini(&self, cloud_config: &CloudConfig) -> Result<Ini, ClusterError> {
        let mut config = Ini::new();
        let session = self.openstack_session(&cloud_config).await?;

        config
            .with_section(Some("Global"))
            .set(
                "auth-url",
                session
                    .get_service_endpoint(&ServiceType::Identity, Some(&ApiVersion::new(3, 0)))?
                    .url_str(),
            )
            .set("region", cloud_config.region_name.clone())
            .set(
                "application-credential-id",
                cloud_config.auth.application_credential_id.clone(),
            )
            .set(
                "application-credential-secret",
                cloud_config.auth.application_credential_secret.clone(),
            )
            .set("tls-insecure", "TODO");

        // TODO(mnaser): fix me
        if false {
            config
                .with_section(Some("Global"))
                .set("ca-file", "/etc/config/ca.crt");
        }

        let octavia_lb_algorithm = match self.labels.octavia_lb_algorithm.clone() {
            Some(algorithm) => {
                if self.labels.octavia_provider == "ovn" && algorithm != "SOURCE_IP_PORT" {
                    return Err(ClusterError::InvalidOctaviaLoadBalancerAlgorithm(algorithm));
                }

                algorithm
            }
            None => match self.labels.octavia_provider.as_str() {
                "amphora" => "ROUND_ROBIN".to_owned(),
                "ovn" => "SOURCE_IP_PORT".to_owned(),
                _ => {
                    return Err(ClusterError::InvalidOctaviaLoadBalancerProvider(
                        self.labels.octavia_provider.clone(),
                    ))
                }
            },
        };

        config
            .with_section(Some("LoadBalancer"))
            .set("lb-provider", self.labels.octavia_provider.clone())
            .set("lb-method", octavia_lb_algorithm)
            .set(
                "create-monitor",
                self.labels.octavia_lb_healthcheck.to_string(),
            );

        // config = configparser.ConfigParser()
        // config["Global"] = {
        //     "auth-url": self.cloud_config["auth"]["auth_url"],
        //     "tls-insecure": "false" if self.cloud_config["verify"] else "true",
        // }
        // config["LoadBalancer"] = {
        //     "floating-network-id": self.floating_network_id,
        //     "network-id": self.network_id,
        //     "subnet-id": self.subnet_id,
        // }

        // return textwrap.dedent(
        //     f"""\
        //     [Global]
        //     auth-url={osc.url_for(service_type="identity", interface="public")}
        //     tls-insecure={"false" if CONF.drivers.verify_ca else "true"}
        //     {"ca-file=/etc/config/ca.crt" if magnum_utils.get_openstack_ca() else ""}
        //     """
        // )

        Ok(config)
    }

    async fn cloud_config_ini_as_string(
        &self,
        cloud_config: &CloudConfig,
    ) -> Result<String, ClusterError> {
        let mut buffer = Vec::new();
        self.cloud_config_ini(cloud_config)
            .await?
            .write_to(&mut buffer)?;

        Ok(String::from_utf8(buffer).expect("failed to convert ini to string"))
    }

    pub async fn cloud_provider_secret<T: ClusterAddon>(
        &self,
        client: &Client,
        addon: &T,
    ) -> Result<Secret, ClusterError> {
        let api: Api<Secret> = Api::namespaced(client.clone(), self.namespace());
        let cloud_identity_secret = api.get(&self.cloud_identity_secret_name()?).await?;
        let clouds_yaml: CloudConfigFile = serde_yaml::from_slice(
            &cloud_identity_secret
                .data
                .expect("missing data field")
                .get("clouds.yaml")
                .expect("missing clouds.yaml field")
                .0,
        )?;
        let default_cloud = clouds_yaml
            .clouds
            .get("default")
            .expect("missing default cloud config");

        let cloud_config_secret = Secret {
            metadata: ObjectMeta {
                name: Some("cloud-config".to_owned()),
                namespace: Some("kube-system".to_owned()),
                ..Default::default()
            },
            string_data: Some(btreemap! {
                "cloud.conf".to_owned() => self.cloud_config_ini_as_string(&default_cloud).await?,
                "ca.crt".to_owned() => "TODO".to_owned(),
            }),
            ..Default::default()
        };

        let data = btreemap! {
            "cloud-controller-manager.yaml".to_owned() => addon.manifests()?,
            "cloud-config-secret.yaml".to_owned() => serde_yaml::to_string(&cloud_config_secret).map_err(ClusterError::Serialization)?,
        };

        Ok(Secret {
            metadata: ObjectMeta {
                name: Some(self.cloud_provider_resource_name()?),
                ..Default::default()
            },
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(data),
            ..Default::default()
        })
    }
}

impl From<&Cluster> for ClusterResourceSet {
    fn from(cluster: &Cluster) -> Self {
        ClusterResourceSet {
            metadata: cluster.into(),
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

impl From<&Cluster> for Secret {
    fn from(cluster: &Cluster) -> Self {
        let mut data = BTreeMap::<String, String>::new();

        let cilium = cilium::Addon::new(cluster.clone());
        if cilium.enabled() {
            data.insert("cilium.yaml".to_owned(), cilium.manifests().unwrap());
        }

        Secret {
            metadata: cluster.into(),
            type_: Some("addons.cluster.x-k8s.io/resource-set".into()),
            string_data: Some(data),
            ..Default::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        addons,
        clients::{kubernetes::fixtures, openstack::CloudConfigAuth},
    };
    use mockall::predicate::*;
    use openstack_sdk::types::identity::v3::{AuthResponse, AuthToken};
    use pretty_assertions::assert_eq;
    use rstest::rstest;
    use serde::Serialize;
    use serde_json::json;
    use serde_yaml::Value;
    use std::path::PathBuf;
    use wiremock::{
        matchers::{method, path},
        Mock, MockServer, ResponseTemplate,
    };

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
        let cluster = &Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let object_meta: ObjectMeta = cluster.into();

        assert_eq!(object_meta.name, Some("sample-uuid".into()));
    }

    #[test]
    fn test_cloud_provider_resource_name_success() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster.cloud_provider_resource_name();
        let expected_resource_name = format!("{}-cloud-provider", cluster.stack_id.unwrap());

        assert!(result.is_ok());
        assert_eq!(result.unwrap(), expected_resource_name);
    }

    #[test]
    fn test_cloud_provider_resource_name_missing_stack_id() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: None,
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster.cloud_provider_resource_name();

        assert!(result.is_err());
        match result {
            Err(ClusterError::MissingStackId(uuid)) => {
                assert_eq!(uuid, cluster.uuid);
            }
            _ => panic!("Expected ClusterError::MissingStackId, got different error"),
        }
    }

    #[test]
    fn test_cloud_provider_cluster_resource_set_success() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
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
    fn test_cloud_provider_cluster_resource_set_missing_stack_id() {
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: None,
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let result = cluster.cloud_provider_cluster_resource_set();

        assert!(result.is_err());
        match result {
            Err(ClusterError::MissingStackId(uuid)) => {
                assert_eq!(uuid, cluster.uuid);
            }
            _ => panic!("Expected ClusterError::MissingStackId, got different error"),
        }
    }

    // TODO: test_openstack_session
    // TODO: refactor mocks

    #[tokio::test]
    async fn test_cloud_config_ini_success() {
        let mock_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
              "versions": {
                "values": [
                  {
                    "id": "v3.14",
                    "status": "stable",
                    "updated": "2020-04-07T00:00:00Z",
                    "links": [
                      {
                        "rel": "self",
                        "href": format!("{}/v3/", mock_server.uri())
                      }
                    ],
                    "media-types": [
                      {
                        "base": "application/json",
                        "type": "application/vnd.openstack.identity-v3+json"
                      }
                    ]
                  }
                ]
              }
            })))
            .expect(1)
            .mount(&mock_server)
            .await;
        Mock::given(method("POST"))
            .and(path("/v3/auth/tokens"))
            .respond_with(
                ResponseTemplate::new(200)
                    .append_header("x-subject-token", "token")
                    .set_body_json(json!(AuthResponse {
                        token: AuthToken {
                            ..Default::default()
                        }
                    })),
            )
            .expect(1)
            .mount(&mock_server)
            .await;

        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let cloud_config = CloudConfig::builder()
            .auth(
                CloudConfigAuth::builder()
                    .application_credential_id("fake-application-credential-id".to_owned())
                    .application_credential_secret("fake-application-credential-secret".to_owned())
                    .auth_url(mock_server.uri())
                    .build(),
            )
            .build();

        let ini = cluster
            .cloud_config_ini(&cloud_config)
            .await
            .expect("failed to generate ini");

        let global = ini.section(Some("Global")).expect("missing global section");
        assert_eq!(
            global.get("auth-url").expect("missing auth-url"),
            mock_server.uri() + "/v3/"
        );
    }

    // TODO: test_cloud_config_ini_as_string

    #[tokio::test]
    async fn test_cloud_provider_secret_success() {
        let mock_server = MockServer::start().await;
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let (client, api_server) = fixtures::get_test_client();
        api_server.run(fixtures::Scenario::GetClusterIdentitySecret(
            cluster.clone(),
            CloudConfig::builder()
                .auth(
                    CloudConfigAuth::builder()
                        .application_credential_id("fake-application-credential-id".to_owned())
                        .application_credential_secret(
                            "fake-application-credential-secret".to_owned(),
                        )
                        .auth_url(mock_server.uri())
                        .build(),
                )
                .build(),
        ));

        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon
            .expect_manifests()
            .return_once(|| Ok("blah".to_string()));

        let result = cluster
            .cloud_provider_secret(&client, &mock_addon)
            .await
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

    #[tokio::test]
    async fn test_cloud_provider_secret_missing_stack_id() {
        let mock_server = MockServer::start().await;
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: None,
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let (client, api_server) = fixtures::get_test_client();
        api_server.run(fixtures::Scenario::GetClusterIdentitySecret(
            cluster.clone(),
            CloudConfig::builder()
                .auth(
                    CloudConfigAuth::builder()
                        .application_credential_id("fake-application-credential-id".to_owned())
                        .application_credential_secret(
                            "fake-application-credential-secret".to_owned(),
                        )
                        .auth_url(mock_server.uri())
                        .build(),
                )
                .build(),
        ));

        let mock_addon = addons::MockClusterAddon::default();
        let result = cluster.cloud_provider_secret(&client, &mock_addon).await;

        assert!(result.is_err());
        match result {
            Err(ClusterError::MissingStackId(uuid)) => {
                assert_eq!(uuid, cluster.uuid);
            }
            _ => panic!("Expected ClusterError::MissingStackId, got different error"),
        }
    }

    #[tokio::test]
    async fn test_cloud_provider_secret_manifest_render_failure() {
        let mock_server = MockServer::start().await;
        let cluster = Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::builder().build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let (client, api_server) = fixtures::get_test_client();
        api_server.run(fixtures::Scenario::GetClusterIdentitySecret(
            cluster.clone(),
            CloudConfig::builder()
                .auth(
                    CloudConfigAuth::builder()
                        .application_credential_id("fake-application-credential-id".to_owned())
                        .application_credential_secret(
                            "fake-application-credential-secret".to_owned(),
                        )
                        .auth_url(mock_server.uri())
                        .build(),
                )
                .build(),
        ));

        let mut mock_addon = addons::MockClusterAddon::default();
        mock_addon.expect_manifests().return_once(|| {
            Err(helm::HelmTemplateError::HelmCommand(
                "helm template failed".to_string(),
            ))
        });

        let result = cluster.cloud_provider_secret(&client, &mock_addon).await;

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
            labels: ClusterLabels::builder().build(),
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
        let cluster = &Cluster {
            uuid: "sample-uuid".to_string(),
            labels: ClusterLabels::default(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: ClusterTemplate {
                network_driver: "calico".to_string(),
            },
        };

        let secret: Secret = cluster.into();

        assert_eq!(secret.metadata.name, Some(cluster.uuid.clone()));
        assert_eq!(
            secret.type_,
            Some("addons.cluster.x-k8s.io/resource-set".into())
        );
    }
}
