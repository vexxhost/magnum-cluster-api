use crate::{
    builder::Values,
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
        },
        kubeadmconfigtemplates::KubeadmConfigTemplate,
        kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplate,
        openstackclustertemplates::OpenStackClusterTemplate,
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::{
        api_server_load_balancer, audit_log, boot_volume, cloud_controller_manager,
        cluster_identity, containerd_config, control_plane_availability_zones,
        disable_api_server_floating_ip, external_network, flavors, image_repository, images,
        keystone_auth, networks, openid_connect, operating_system, server_groups, ssh_key, tls,
        volumes, KUBEADM_CONFIG_TEMPLATE, KUBEADM_CONTROL_PLANE_TEMPLATE,
        OPENSTACK_CLUSTER_TEMPLATE, OPENSTACK_MACHINE_TEMPLATE,
    },
};
use base64::prelude::*;
use indoc::indoc;
use json_patch::{patch, AddOperation, Patch, PatchOperation, RemoveOperation, ReplaceOperation};
use jsonptr::PointerBuf;
use kube::Resource;
use serde::{de::DeserializeOwned, Serialize};
use serde_gtmpl::ToGtmplValue;
use serde_json::json;

/// A trait for converting a value into a [`Patch`] using provided template
/// values.
///
/// This trait abstracts the conversion process, allowing different types to
/// be rendered into a [`Patch`] by supplying template parameters. The provided
/// value must be convertible into a [`gtmpl::Value`] and be clonable so that
/// it can be reused during the conversion process.
pub trait ToPatch {
    fn to_patch<T: Serialize + ToGtmplValue>(self, values: &T) -> Patch;
}

/// Implements the [`ToPatch`] trait for a vector of patch definitions.
///
/// Each element in the vector is converted into a rendered patch using the
/// provided template values.  The method iterates over all patches, rendering
/// each one individually via [`ClusterClassPatchesDefinitionsJsonPatches::to_rendered_patch`],
/// and then collects the results into a single [`Patch`].
impl ToPatch for Vec<ClusterClassPatchesDefinitionsJsonPatches> {
    fn to_patch<T: Serialize + ToGtmplValue>(self, values: &T) -> Patch {
        Patch(
            self.into_iter()
                .map(|patch| patch.to_rendered_patch(values))
                .collect(),
        )
    }
}

/// A trait for converting a patch definition into a rendered JSON patch
/// operation.
///
/// This trait provides a method to transform a patch definition into a fully
/// rendered [`PatchOperation`].  The rendering process uses a supplied
/// value—convertible into a  [`gtmpl::Value`]—to resolve any templated content
/// in the patch.
pub trait ToRenderedPatchOperation {
    fn to_rendered_patch<T: Serialize + ToGtmplValue>(self, values: &T) -> PatchOperation;
}

/// Implements [`ToRenderedPatchOperation`] for [`ClusterClassPatchesDefinitionsJsonPatches`].
///
/// This implementation converts an instance of [`ClusterClassPatchesDefinitionsJsonPatches`]
/// into a rendered [`PatchOperation`]. It first determines the value to use in the patch:
///
/// - If [`ClusterClassPatchesDefinitionsJsonPatches::value_from`] is present, it renders
///   the value using the provided template values.
/// - Otherwise, it expects that [`ClusterClassPatchesDefinitionsJsonPatches::value`] is
///   present and converts it directly.
///
/// Depending on the operation specified in the [`ClusterClassPatchesDefinitionsJsonPatches::op`]
/// field, it creates one of the following:
///
/// - `add`: Returns an [`AddOperation`] with a parsed path and the rendered value.
/// - `replace`: Returns a [`ReplaceOperation`] with a parsed path and the rendered value.
/// - `remove`: Returns a [`RemoveOperation`] with a parsed path.
///
/// This method will panic if an unsupported patch operation is encountered.
impl ToRenderedPatchOperation for ClusterClassPatchesDefinitionsJsonPatches {
    fn to_rendered_patch<T: Serialize + ToGtmplValue>(self, values: &T) -> PatchOperation {
        let value = match self.value_from {
            Some(value_from) => value_from.to_rendered_value(values),
            None => self.value.expect("value should be present").into(),
        };

        match self.op.as_str() {
            "add" => json_patch::PatchOperation::Add(AddOperation {
                path: PointerBuf::parse(&self.path).unwrap(),
                value: value,
            }),
            "replace" => json_patch::PatchOperation::Replace(ReplaceOperation {
                path: PointerBuf::parse(&self.path).unwrap(),
                value: value,
            }),
            "remove" => json_patch::PatchOperation::Remove(RemoveOperation {
                path: PointerBuf::parse(&self.path).unwrap(),
            }),
            _ => panic!("Unsupported patch operation: {}", self.op),
        }
    }
}

/// A trait for converting a patch definition's dynamic source into a rendered
/// JSON value.
///
/// The `ToRenderedValue` trait abstracts the process of converting a template
/// or variable into a concrete [`serde_json::Value`] using provided template
/// parameters.  This is useful for dynamically generating configuration values
/// or patch contents.
pub trait ToRenderedValue {
    fn to_rendered_value<T: Serialize + ToGtmplValue>(self, values: &T) -> serde_json::Value;
}

/// Implements [`ToRenderedValue`] for [`ClusterClassPatchesDefinitionsJsonPatchesValueFrom`].
///
/// This implementation converts an instance of [`ClusterClassPatchesDefinitionsJsonPatchesValueFrom`]
/// into a rendered JSON value by following these steps:
///
/// 1. **Template Selection:**
///    - If the `template` field is present, it is cloned and used as the template.
///    - Otherwise, if the `variable` field is available, a default template is
///      generated in the form `{{ .<variable> }}`.
///    - If neither is provided, the code reaches an unreachable state.
///
/// 2. **Template Rendering:**
///    - The chosen template is rendered using the [`gtmpl::template`] function
///      with the provided values. This step is expected to succeed; otherwise,
///      the function will panic.
///
/// 3. **Output Parsing:**
///    - When a template was explicitly provided, the rendered output is parsed
///      as YAML to obtain a [`serde_json::Value`].
///    - If no template was provided, the rendered output is wrapped in a JSON string.
impl ToRenderedValue for ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
    fn to_rendered_value<T: Serialize + ToGtmplValue>(self, values: &T) -> serde_json::Value {
        if self.variable.is_some() {
            let variable = self.variable.as_ref().unwrap();

            if !variable.contains('.') {
                let json =
                    serde_json::to_value(values).expect("serialization to json should succeed");

                if let serde_json::Value::Object(map) = json {
                    if let Some(value) = map.get(variable) {
                        return value.clone();
                    }
                }

                unimplemented!("variable should be present in values");
            }
        }

        let values = values.to_gtmpl_value();
        let template = match self.template.clone() {
            Some(template) => template,
            None => match self.variable {
                Some(variable) => format!("{{{{ .{} }}}}", variable),
                None => unreachable!(),
            },
        };

        let rendered_value =
            gtmpl::template(&template, values).expect("template rendering should succeed");

        match self.template {
            Some(_) => {
                serde_yaml::from_str(&rendered_value).expect("rendered value should be valid YAML")
            }
            None => serde_json::Value::String(rendered_value),
        }
    }
}

/// A trait for applying a JSON patch to a mutable resource.
///
/// Types implementing this trait can have a patch applied that updates their
/// state based on a provided [`Patch`]. The patch operation is intended to
/// modify the resource in-place.
pub trait ApplyPatch {
    fn apply_patch(&mut self, patch: &Patch);
}

/// Implements the [`ApplyPatch`] trait for any Kubernetes [`Resource`] type
/// that supports serialization and deserialization.
///
/// This implementation is generic over types that implement [`Resource`], [`Serialize`],
/// and [`DeserializeOwned`]. It performs the patch application by following these steps:
///
/// 1. Converts the current resource into a JSON document using the [`json!`] macro.
/// 2. Applies the patch to the JSON document via the [`patch`] function, which
///    mutates the document in place. It panics if the patch operation fails.
/// 3. Converts the patched JSON document back into the resource, replacing the
///    original state.  This step will panic if the document is not a valid
///    representation of the resource.
impl<T: Resource + Serialize + DeserializeOwned> ApplyPatch for T {
    fn apply_patch(&mut self, p: &Patch) {
        let mut doc = json!(self);
        patch(&mut doc, p).expect("patch should apply");
        *self = serde_json::from_value(doc).expect("doc should be a valid object")
    }
}

/// A trait for evaluating whether a cluster class patch is enabled based on
/// dynamic template values.
///
/// Implementors of this trait provide a mechanism to determine if a particular
/// patch should be applied.
pub trait ClusterClassPatchEnabled {
    fn is_enabled<T: ToGtmplValue>(&self, values: &T) -> bool;
}

/// Implements [`ClusterClassPatchEnabled`] for [`ClusterClassPatches`].
///
/// This implementation checks the [`ClusterClassPatches::enabled_if`] field,
/// which must be set, and uses it as a template.  The template is rendered
/// with the provided values using `gtmpl::template`. If the rendered output
/// is equal to `"true"`, the patch is considered enabled.
impl ClusterClassPatchEnabled for ClusterClassPatches {
    fn is_enabled<T: ToGtmplValue>(&self, values: &T) -> bool {
        self.enabled_if.as_deref().map_or(true, |enabled_if| {
            let output = gtmpl::template(enabled_if, values.to_gtmpl_value())
                .expect("template rendering should succeed");

            output == "true"
        })
    }
}

/// This is a static instance of the `TestClusterResources` that is used for
/// testing purposes.
pub struct TestClusterResources {
    pub control_plane_openstack_machine_template: OpenStackMachineTemplate,
    pub kubeadm_config_template: KubeadmConfigTemplate,
    pub kubeadm_control_plane_template: KubeadmControlPlaneTemplate,
    pub openstack_cluster_template: OpenStackClusterTemplate,
    pub worker_openstack_machine_template: OpenStackMachineTemplate,
}

impl TestClusterResources {
    pub fn new() -> Self {
        Self {
            control_plane_openstack_machine_template: OPENSTACK_MACHINE_TEMPLATE.clone(),
            kubeadm_config_template: KUBEADM_CONFIG_TEMPLATE.clone(),
            kubeadm_control_plane_template: KUBEADM_CONTROL_PLANE_TEMPLATE.clone(),
            openstack_cluster_template: OPENSTACK_CLUSTER_TEMPLATE.clone(),
            worker_openstack_machine_template: OPENSTACK_MACHINE_TEMPLATE.clone(),
        }
    }

    pub fn apply_patches<T: Serialize + DeserializeOwned + ToGtmplValue>(
        &mut self,
        patches: &Vec<ClusterClassPatches>,
        values: &T,
    ) {
        patches
            .iter()
            .filter(|p| p.is_enabled(values))
            .for_each(|p| {
                let definitions = p.definitions.as_ref().expect("definitions should be set");

                definitions.iter().for_each(|definition| {
                    let patch = definition.json_patches.clone().to_patch(values);

                    match (
                        definition.selector.api_version.as_str(),
                        definition.selector.kind.as_str(),
                    ) {
                        (
                            "controlplane.cluster.x-k8s.io/v1beta1",
                            "KubeadmControlPlaneTemplate",
                        ) => {
                            self.kubeadm_control_plane_template.apply_patch(&patch);
                        }
                        ("infrastructure.cluster.x-k8s.io/v1beta1", "OpenStackClusterTemplate") => {
                            self.openstack_cluster_template.apply_patch(&patch);
                        }
                        ("infrastructure.cluster.x-k8s.io/v1beta1", "OpenStackMachineTemplate") => {
                            let match_resources = &definition.selector.match_resources;

                            if match_resources.control_plane.unwrap_or(false) {
                                self.control_plane_openstack_machine_template
                                    .apply_patch(&patch);
                            }

                            if let Some(machine_deployment_class) =
                                &match_resources.machine_deployment_class
                            {
                                if let Some(names) = &machine_deployment_class.names {
                                    if names.contains(&"default-worker".to_string()) {
                                        self.worker_openstack_machine_template.apply_patch(&patch);
                                    }
                                }
                            }

                            if !match_resources.control_plane.unwrap_or(false)
                                && match_resources.machine_deployment_class.is_none()
                            {
                                unimplemented!(
                                    "Unsupported match resources: {:?}",
                                    match_resources
                                );
                            }
                        }
                        ("bootstrap.cluster.x-k8s.io/v1beta1", "KubeadmConfigTemplate") => {
                            self.kubeadm_config_template.apply_patch(&patch);
                        }
                        _ => unimplemented!(
                            "Unsupported resource type: {}/{}",
                            definition.selector.api_version,
                            definition.selector.kind
                        ),
                    }
                })
            });
    }
}

pub fn default_values() -> Values {
    Values::builder()
        .api_server_load_balancer(
            api_server_load_balancer::APIServerLoadBalancerConfig::builder()
                .enabled(true)
                .provider("amphora".into())
                .build(),
        )
        .audit_log(
            audit_log::AuditLogConfig::builder()
                .enabled(false)
                .max_age("30".to_string())
                .max_backup("10".to_string())
                .max_size("100".to_string())
                .build(),
        )
        .boot_volume(boot_volume::BootVolumeConfig::builder().r#type("nvme".into()).size(0).build())
        .cloud_ca_certificate(cloud_controller_manager::CloudCACertificatesConfig(
            BASE64_STANDARD.encode(indoc!(
                r#"
                -----BEGIN CERTIFICATE-----
                MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzZz5z5z5z5z5z5z5z5z
                -----END CERTIFICATE-----
                "#
            )),
        ))
        .cloud_controller_manager_config(cloud_controller_manager::CloudControllerManagerConfig(BASE64_STANDARD.encode(
            indoc!(
                r#"
                [Global]
                auth-url=https://auth.vexxhost.net
                region=sjc1
                application-credential-id=foo
                application-credential-secret=bar
                tls-insecure=true
                ca-file=/etc/config/ca.crt
                [LoadBalancer]
                lb-provider=amphora
                lb-method=ROUND_ROBIN
                create-monitor=true
                "#,
            ),
        )))
        .cluster_identity_ref_name(cluster_identity::Config("identity-ref-name".into()))
        .containerd_config(containerd_config::ContainerdConfig(
            BASE64_STANDARD.encode(indoc! {r#"
                # Use config version 2 to enable new configuration fields.
                # Config file is parsed as version 1 by default.
                version = 2

                imports = ["/etc/containerd/conf.d/*.toml"]

                [plugins]
                [plugins."io.containerd.grpc.v1.cri"]
                    sandbox_image = "{sandbox_image}"
                [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
                    runtime_type = "io.containerd.runc.v2"
                [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
                    SystemdCgroup = true
            "#})
        ))
        .systemd_proxy_config(containerd_config::SystemdProxyConfig(BASE64_STANDARD.encode(indoc! {r#"
            [Service]
            Environment="http_proxy=http://proxy.internal:3128"
            Environment="HTTP_PROXY=http://proxy.internal:3128"
            Environment="https_proxy=https://proxy.internal:3129"
            Environment="HTTPS_PROXY=https://proxy.internal:3129"
            Environment="no_proxy=localhost,
            Environment="NO_PROXY=localhost,
        "#})))
        .control_plane_availability_zones(control_plane_availability_zones::Config(vec![
            "zone1".into(),
            "zone2".into(),
        ]))
        .disable_api_server_floating_ip(disable_api_server_floating_ip::Config(true))
        .external_network_id(external_network::Config("external-network-id".into()))
        .control_plane_flavor(flavors::ControlPlaneFlavorConfig("control-plane".into()))
        .flavor(flavors::WorkerFlavorConfig("worker".into()))
        .image_repository(image_repository::Config("registry.example.com/cluster-api".into()))
        .image_uuid(images::Config("bar".into()))
        .enable_keystone_auth(keystone_auth::Config(true))
        .node_cidr(networks::NodeCIDRConfig("foo".into()))
        .dns_nameservers(networks::DNSNameserversConfig(vec!["1.1.1.1".into()]))
        .fixed_network_id(networks::FixedNetworkIDConfig("foo".into()))
        .fixed_subnet_id(networks::FixedSubnetIDConfig("bar".into()))
        .openid_connect(
            openid_connect::OpenIdConnectConfig::builder()
                .issuer_url("https://example.com".to_string())
                .client_id("client-id".to_string())
                .username_claim("email".to_string())
                .username_prefix("email:".to_string())
                .groups_claim("groups".to_string())
                .groups_prefix("groups:".to_string())
                .build(),
        )
        .operating_system(operating_system::OperatingSystemConfig(operating_system::OperatingSystem::Ubuntu))
        .apt_proxy_config(operating_system::AptProxyConfig("bar".into()))
        .server_group_id(server_groups::ServerGroupIDConfig(
            "server-group-1".to_string(),
        ))
        .is_server_group_diff_failure_domain(server_groups::DifferentFailureDomainConfig(true))
        .ssh_key_name(ssh_key::Config("my-key".into()))
        .api_server_tls_cipher_suites(tls::ApiServerTLSCipherSuitesConfig("TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305".into()))
        .api_server_sans(tls::ApiServerSANsConfig("".into()))
        .kubelet_tls_cipher_suites(tls::KubeletTLSCipherSuitesConfig("TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305".into()))
        .enable_docker_volume(volumes::EnableDockerVolumeConfig(false))
        .docker_volume_size(volumes::DockerVolumeSizeConfig(0))
        .docker_volume_type(volumes::DockerVolumeTypeConfig("".into()))
        .enable_etcd_volume(volumes::EnableEtcdVolumeConfig(false))
        .etcd_volume_size(volumes::EtcdVolumeSizeConfig(0))
        .etcd_volume_type(volumes::EtcdVolumeTypeConfig("".into()))
        .availability_zone(volumes::AvailabilityZoneConfig("az1".into()))
        .build()
}
