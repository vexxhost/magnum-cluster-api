use crate::cluster_api::{
    kubeadmcontrolplanetemplates::{
        KubeadmControlPlaneTemplate, KubeadmControlPlaneTemplateSpec,
        KubeadmControlPlaneTemplateTemplate, KubeadmControlPlaneTemplateTemplateSpec,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer,
        KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes,
    },
    openstackclustertemplates::{
        OpenStackClusterTemplate, OpenStackClusterTemplateSpec, OpenStackClusterTemplateTemplate,
        OpenStackClusterTemplateTemplateSpec, OpenStackClusterTemplateTemplateSpecIdentityRef,
        OpenStackClusterTemplateTemplateSpecManagedSecurityGroups,
    },
};
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
};
use json_patch::{patch, AddOperation, Patch, PatchOperation, RemoveOperation, ReplaceOperation};
use jsonptr::PointerBuf;
use kube::Resource;
use maplit::btreemap;
use pretty_assertions::assert_eq;
use serde::{de::DeserializeOwned, Serialize};
use serde_gtmpl::ToGtmplValue;
use serde_json::json;
use std::{collections::BTreeMap, sync::LazyLock};

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

/// Asserts that every key-value pair in the `needle` map is present in the
/// `haystack` map.
///
/// This function checks that `needle` is a subset of `haystack` by iterating
/// over the keys in `needle` and extracting the corresponding values from
/// `haystack`. It then compares the extracted subset (with values wrapped in
/// `Some`) to `needle` (with its values also wrapped in `Some`).
///
/// # Example
///
/// ```rust
/// use std::collections::BTreeMap;
///
/// // Example maps
/// let mut needle = BTreeMap::new();
/// needle.insert("a", 1);
///
/// let mut haystack = BTreeMap::new();
/// haystack.insert("a", 1);
/// haystack.insert("b", 2);
///
/// // This assertion will pass since all key-value pairs in `needle` are in `haystack`.
/// assert_subset_of_btreemap(&needle, &haystack);
/// ```
pub fn assert_subset_of_btreemap<
    K: Ord + std::fmt::Debug + Clone,
    V: PartialEq + std::fmt::Debug + Clone,
>(
    needle: &BTreeMap<K, V>,
    haystack: &BTreeMap<K, V>,
) {
    let mut extracted_haystack: BTreeMap<K, Option<V>> = BTreeMap::new();

    for needle_key in needle.keys() {
        let haystack_value = haystack.get(needle_key).cloned();
        extracted_haystack.insert(needle_key.clone(), haystack_value);
    }

    let needle_with_options: BTreeMap<K, Option<V>> = needle
        .iter()
        .map(|(k, v)| (k.clone(), Some(v.clone())))
        .collect();

    assert_eq!(needle_with_options, extracted_haystack);
}

/// This is a static instance of the `KubeadmControlPlaneTemplate` that is
/// used as a default for testing, since we have not yet migrated the
/// resource into the Rust API.
pub static KCPT_WIP: LazyLock<KubeadmControlPlaneTemplate> = LazyLock::new(|| {
    KubeadmControlPlaneTemplate {
    metadata: Default::default(),
    spec: KubeadmControlPlaneTemplateSpec {
        template: KubeadmControlPlaneTemplateTemplate {
            spec: KubeadmControlPlaneTemplateTemplateSpec {
                kubeadm_config_spec: KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpec {
                    cluster_configuration: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfiguration {
                        api_server: Some(KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServer {
                            extra_args: Some({
                                btreemap! {
                                    "cloud-provider".to_string() => "external".to_string(),
                                    "profiling".to_string() => "false".to_string(),
                                }
                            }),
                            // Note(oleks): Add this as default as a workaround of the json patch limitation # noqa: E501
                            // https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass#json-patches-tips--tricks
                            extra_volumes: Some(vec![
                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecClusterConfigurationApiServerExtraVolumes {
                                    name: "webhooks".to_string(),
                                    host_path: "/etc/kubernetes/webhooks".to_string(),
                                    mount_path: "/etc/kubernetes/webhooks".to_string(),
                                    ..Default::default()
                                }
                            ]),
                            ..Default::default()
                        }),
                        ..Default::default()
                    }),
                    files: Some(vec![]),
                    pre_kubeadm_commands: Some(vec![]),
                    post_kubeadm_commands: Some(vec![]),
                    ..Default::default()
                },
                ..Default::default()
            },
            ..Default::default()
        },
        ..Default::default()
    }
}
});

/// This is a static instance of the `OpenStackClusterTemplate` that is
/// used as a default for testing, since we have not yet migrated the
/// resource into the Rust API.
pub static OCT_WIP: LazyLock<OpenStackClusterTemplate> =
    LazyLock::new(|| OpenStackClusterTemplate {
        metadata: Default::default(),
        spec: OpenStackClusterTemplateSpec {
            template: OpenStackClusterTemplateTemplate {
                spec: OpenStackClusterTemplateTemplateSpec {
                    identity_ref: OpenStackClusterTemplateTemplateSpecIdentityRef {
                        name: "PLACEHOLDER".into(),
                        cloud_name: "default".into(),
                        ..Default::default()
                    },
                    managed_security_groups: Some(
                        OpenStackClusterTemplateTemplateSpecManagedSecurityGroups {
                            allow_all_in_cluster_traffic: true,
                            ..Default::default()
                        },
                    ),
                    ..Default::default()
                },
                ..Default::default()
            },
            ..Default::default()
        },
    });

/// This is a static instance of the `TestClusterResources` that is used for
/// testing purposes.
pub struct TestClusterResources {
    pub kubeadm_control_plane_template: KubeadmControlPlaneTemplate,
    pub openstack_cluster_template: OpenStackClusterTemplate,
}

impl TestClusterResources {
    pub fn new() -> Self {
        Self {
            kubeadm_control_plane_template: KCPT_WIP.clone(),
            openstack_cluster_template: OCT_WIP.clone(),
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
