// Copyright (c) 2024 VEXXHOST, Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License"); you may
// not use this file except in compliance with the License. You may obtain
// a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
// WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
// License for the specific language governing permissions and limitations
// under the License.

//! Calico CNI addon for Magnum Cluster API.
//!
//! Calico is deployed via vendored static YAML manifests (one per version),
//! stored in `magnum_cluster_api/manifests/calico/`.  When `auto_upgrade_cni`
//! is enabled on the cluster, the Calico addon creates a dedicated
//! ClusterResourceSet with `strategy: Reconcile` and updates the associated
//! Secret with the manifest for the requested `calico_tag`.  This allows CAPI
//! to re-apply Calico on the workload cluster, effectively upgrading it.
//!
//! See: <https://github.com/vexxhost/magnum-cluster-api/issues/919>

use crate::{
    addons::ClusterAddon,
    magnum::{self, ClusterError},
};
use include_dir::{include_dir, Dir};
use maplit::btreemap;
use std::collections::BTreeMap;

/// All vendored Calico manifests, embedded at compile time.
///
/// Each file is named `<version>.yaml`, e.g. `v3.27.4.yaml`.
static CALICO_MANIFESTS: Dir<'_> =
    include_dir!("$CARGO_MANIFEST_DIR/magnum_cluster_api/manifests/calico");

pub struct Addon {
    cluster: magnum::Cluster,
}

impl Addon {
    /// Apply `container_infra_prefix` image mirroring to a Calico manifest.
    ///
    /// Calico manifests reference images under `quay.io/calico/`.  When a
    /// custom registry prefix is configured, those references are rewritten to
    /// `{registry}/calico/` so that air-gapped or mirrored deployments work.
    fn apply_image_prefix(content: String, registry: &Option<String>) -> String {
        match registry {
            Some(registry) => content.replace(
                "quay.io/calico/",
                &format!("{}/calico/", registry.trim_end_matches('/')),
            ),
            None => content,
        }
    }
}

impl ClusterAddon for Addon {
    fn new(cluster: magnum::Cluster) -> Self {
        Self { cluster }
    }

    fn enabled(&self) -> bool {
        self.cluster.cluster_template.network_driver == "calico"
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-calico", self.cluster.stack_id()?))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        let calico_tag = &self.cluster.labels.calico_tag;
        let filename = format!("{}.yaml", calico_tag);

        let raw = CALICO_MANIFESTS
            .get_file(&filename)
            .and_then(|f| f.contents_utf8())
            .ok_or_else(|| {
                helm::HelmTemplateError::HelmCommand(format!(
                    "Calico manifest not found for version: {} (expected file: {})",
                    calico_tag, filename
                ))
            })?
            .to_owned();

        let content =
            Self::apply_image_prefix(raw, &self.cluster.labels.container_infra_prefix);

        Ok(btreemap! {
            "calico.yaml".to_owned() => content,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;
    use rstest::rstest;

    fn make_cluster(network_driver: &str, calico_tag: &str) -> magnum::Cluster {
        magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .calico_tag(calico_tag.to_owned())
                .build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: magnum::ClusterTemplate {
                network_driver: network_driver.to_string(),
            },
            ..Default::default()
        }
    }

    #[test]
    fn test_calico_addon_enabled() {
        let cluster = make_cluster("calico", "v3.27.4");
        let addon = Addon::new(cluster);
        assert!(addon.enabled());
    }

    #[test]
    fn test_calico_addon_disabled_for_cilium() {
        let cluster = make_cluster("cilium", "v3.27.4");
        let addon = Addon::new(cluster);
        assert!(!addon.enabled());
    }

    #[test]
    fn test_calico_addon_secret_name() {
        let cluster = make_cluster("calico", "v3.27.4");
        let addon = Addon::new(cluster);
        assert_eq!(addon.secret_name().unwrap(), "kube-abcde-calico");
    }

    #[test]
    fn test_calico_addon_manifests_known_version() {
        let cluster = make_cluster("calico", "v3.27.4");
        let addon = Addon::new(cluster);
        let manifests = addon.manifests().expect("should return manifests");
        assert!(
            manifests.contains_key("calico.yaml"),
            "expected 'calico.yaml' key in manifests"
        );
        let content = &manifests["calico.yaml"];
        assert!(!content.is_empty(), "manifest content should not be empty");
    }

    #[test]
    fn test_calico_addon_manifests_unknown_version() {
        let cluster = make_cluster("calico", "v9.99.99");
        let addon = Addon::new(cluster);
        let result = addon.manifests();
        assert!(result.is_err(), "should fail for unknown version");
        match result.unwrap_err() {
            helm::HelmTemplateError::HelmCommand(msg) => {
                assert!(msg.contains("v9.99.99"), "error should mention the version");
            }
            _ => panic!("expected HelmCommand error"),
        }
    }

    #[test]
    fn test_calico_addon_manifests_image_prefix() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .calico_tag("v3.27.4".to_owned())
                .container_infra_prefix(Some("registry.example.com".to_owned()))
                .build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };
        let addon = Addon::new(cluster);
        let manifests = addon.manifests().expect("should return manifests");
        let content = &manifests["calico.yaml"];
        assert!(
            !content.contains("quay.io/calico/"),
            "quay.io/calico/ should have been replaced"
        );
        assert!(
            content.contains("registry.example.com/calico/"),
            "registry.example.com/calico/ should appear in manifest"
        );
    }

    #[test]
    fn test_calico_addon_manifests_image_prefix_trailing_slash() {
        // Registry with a trailing slash should not produce double slashes
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .calico_tag("v3.27.4".to_owned())
                .container_infra_prefix(Some("registry.example.com/".to_owned()))
                .build(),
            stack_id: Some("kube-abcde".to_string()),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "calico".to_string(),
            },
            ..Default::default()
        };
        let addon = Addon::new(cluster);
        let manifests = addon.manifests().expect("should return manifests");
        let content = &manifests["calico.yaml"];
        assert!(
            !content.contains("quay.io/calico/"),
            "quay.io/calico/ should have been replaced"
        );
        assert!(
            !content.contains("registry.example.com//calico/"),
            "double slashes must not appear in image refs"
        );
        assert!(
            content.contains("registry.example.com/calico/"),
            "registry.example.com/calico/ should appear in manifest"
        );
    }

    #[rstest]
    #[case("v3.24.2")]
    #[case("v3.25.2")]
    #[case("v3.26.5")]
    #[case("v3.27.4")]
    #[case("v3.28.2")]
    #[case("v3.29.0")]
    #[case("v3.29.2")]
    #[case("v3.29.3")]
    #[case("v3.30.0")]
    #[case("v3.30.1")]
    #[case("v3.30.2")]
    #[case("v3.31.3")]
    fn test_calico_addon_manifests_all_known_versions(#[case] calico_tag: &str) {
        let cluster = make_cluster("calico", calico_tag);
        let addon = Addon::new(cluster);
        let manifests = addon
            .manifests()
            .expect("all bundled calico versions should render manifests");
        assert!(
            manifests.contains_key("calico.yaml"),
            "expected calico.yaml key for version {}",
            calico_tag
        );
        assert!(
            !manifests["calico.yaml"].is_empty(),
            "manifest content must not be empty for version {}",
            calico_tag
        );
    }
}
