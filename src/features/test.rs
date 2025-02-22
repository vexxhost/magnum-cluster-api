use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
};
use gtmpl::Value;
use json_patch::{patch, AddOperation, Patch, PatchOperation, RemoveOperation, ReplaceOperation};
use jsonptr::PointerBuf;
use kube::Resource;
use pretty_assertions::assert_eq;
use serde::{de::DeserializeOwned, Serialize};
use serde_json::json;
use std::collections::BTreeMap;

pub trait ToPatch {
    fn to_patch<T: Into<gtmpl::Value> + Clone>(self, values: T) -> Patch;
}

impl ToPatch for Vec<ClusterClassPatchesDefinitionsJsonPatches> {
    fn to_patch<T: Into<gtmpl::Value> + Clone>(self, values: T) -> Patch {
        Patch(
            self.into_iter()
                .map(|patch| patch.to_rendered_patch(values.clone().into()))
                .collect(),
        )
    }
}

pub trait ToRenderedPatchOperation {
    fn to_rendered_patch<T: Into<gtmpl::Value>>(self, values: T) -> PatchOperation;
}

impl ToRenderedPatchOperation for ClusterClassPatchesDefinitionsJsonPatches {
    fn to_rendered_patch<T: Into<gtmpl::Value>>(self, values: T) -> PatchOperation {
        let value = match self.value_from {
            Some(value_from) => value_from.to_rendered_value(values),
            None => self.value.expect("value should be present").to_string(),
        };

        match self.op.as_str() {
            "add" => json_patch::PatchOperation::Add(AddOperation {
                path: PointerBuf::parse(&self.path).unwrap(),
                value: value.into(),
            }),
            "replace" => json_patch::PatchOperation::Replace(ReplaceOperation {
                path: PointerBuf::parse(&self.path).unwrap(),
                value: value.into(),
            }),
            "remove" => json_patch::PatchOperation::Remove(RemoveOperation {
                path: PointerBuf::parse(&self.path).unwrap(),
            }),
            _ => panic!("Unsupported patch operation: {}", self.op),
        }
    }
}

pub trait ToRenderedValue {
    fn to_rendered_value<T: Into<Value>>(self, values: T) -> String;
}

impl ToRenderedValue for ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
    fn to_rendered_value<T: Into<Value>>(self, values: T) -> String {
        let template = match self.template {
            Some(template) => template,
            None => match self.variable {
                Some(variable) => format!("{{{{ .{} }}}}", variable),
                None => unreachable!(),
            },
        };

        gtmpl::template(&template, values).expect("template rendering should succeed")
    }
}

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

pub trait ApplyPatch {
    fn apply_patch(&mut self, patch: &Patch);
}

impl<T: Resource + Serialize + DeserializeOwned> ApplyPatch for T {
    fn apply_patch(&mut self, p: &Patch) {
        let mut doc = json!(self);
        patch(&mut doc, p).expect("patch should apply");
        *self = serde_json::from_value(doc).expect("doc should be a valid object")
    }
}

pub trait ClusterClassPatchEnabled {
    fn is_enabled<T: Into<Value>>(&self, values: T) -> bool;
}

impl ClusterClassPatchEnabled for ClusterClassPatches {
    fn is_enabled<T: Into<Value>>(&self, values: T) -> bool {
        let enabled_if = self
            .enabled_if
            .as_deref()
            .expect("enabled_if should be set");

        let output =
            gtmpl::template(enabled_if, values).expect("template rendering should succeed");

        output == "true"
    }
}
