use crate::{
    addons::ClusterAddon,
    magnum::{self, ClusterError},
};
use include_dir::{include_dir, Dir};
use lazy_static::lazy_static;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};

// Include the manifest directories at compile time
// These should match the available versions supported by the snapshot_controller_csi_tag field
static V7_0_2_DIR: Dir<'_> = include_dir!("magnum_cluster_api/manifests/snapshot-controller-csi/v7.0.2");
static V8_2_1_DIR: Dir<'_> = include_dir!("magnum_cluster_api/manifests/snapshot-controller-csi/v8.2.1");

// Define a map of version tags to embedded directories
// This allows for more flexible version handling
lazy_static! {
    static ref MANIFEST_DIRS: HashMap<&'static str, &'static Dir<'static>> = {
        let mut m = HashMap::new();
        m.insert("v7.0.2", &V7_0_2_DIR);
        m.insert("v8.2.1", &V8_2_1_DIR);
        m
    };
}

/// Represents the image values for the snapshot controller.
#[derive(Debug, Deserialize, PartialEq, Serialize)]
struct SnapshotControllerImage {
    /// The image name without tag.
    repository: String,
    /// The tag to use for the image.
    tag: String,
}

/// Addon implementation for the snapshot-controller-csi.
pub struct Addon {
    cluster: magnum::Cluster,
}

impl Addon {
    /// Generates the setup-snapshot-controller.yaml manifest with the specified tag
    fn generate_setup_snapshot_controller_manifest(&self, tag: &str) -> String {
        // Determine the image path - either with custom registry or default
        let image_path = match &self.cluster.labels.container_infra_prefix {
            Some(prefix) => {
                let prefix = prefix.trim_end_matches('/');
                // When using a custom registry, the image is named 'csi-snapshot-controller'
                format!("{}/csi-snapshot-controller:{}", prefix, tag)
            },
            None => {
                // For the default registry, it's named 'snapshot-controller'
                format!("registry.k8s.io/sig-storage/snapshot-controller:{}", tag)
            }
        };

        // Generate the manifest with the appropriate image tag
        format!(r#"# This YAML file shows how to deploy the snapshot controller

# The snapshot controller implements the control loop for CSI snapshot functionality.
# It should be installed as part of the base Kubernetes distribution in an appropriate
# namespace for components implementing base system functionality. For installing with
# Vanilla Kubernetes, kube-system makes sense for the namespace.

---
kind: Deployment
apiVersion: apps/v1
metadata:
  name: snapshot-controller
  namespace: kube-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: snapshot-controller
  # The snapshot controller won't be marked as ready if the v1 CRDs are unavailable.
  # The flag --retry-crd-interval-max is used to determine how long the controller
  # will wait for the CRDs to become available before exiting. The default is 30 seconds
  # so minReadySeconds should be set slightly higher than the flag value.
  minReadySeconds: 35
  strategy:
    rollingUpdate:
      maxSurge: 0
      maxUnavailable: 1
    type: RollingUpdate
  template:
    metadata:
      labels:
        app.kubernetes.io/name: snapshot-controller
    spec:
      serviceAccountName: snapshot-controller
      containers:
        - name: snapshot-controller
          image: {image_path}
          args:
            - "--v=5"
            - "--leader-election=true"
          imagePullPolicy: IfNotPresent
"#)
    }

    /// Generates the cinder-snapshot-class.yaml manifest when Cinder CSI is enabled
    fn generate_cinder_snapshot_class_manifest(&self) -> String {
        r#"# This manifest defines a VolumeSnapshotClass for the Cinder CSI driver
# It enables taking volume snapshots with the Cinder CSI driver

---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: block-snapshot
  annotations:
    snapshot.storage.kubernetes.io/is-default-class: "true"
driver: cinder.csi.openstack.org
deletionPolicy: Delete
"#.to_string()
    }

    /// Generates the manila-snapshot-class.yaml manifest when Manila CSI is enabled
    fn generate_manila_snapshot_class_manifest(&self) -> String {
        r#"# This manifest defines a VolumeSnapshotClass for the Manila CSI driver
# It enables taking volume snapshots with the Manila CSI driver

---
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: share-snapshot
  annotations:
    snapshot.storage.kubernetes.io/is-default-class: "true"
driver: manila.csi.openstack.org
deletionPolicy: Delete
"#.to_string()
    }
}

impl ClusterAddon for Addon {
    fn new(cluster: magnum::Cluster) -> Self {
        Self { cluster }
    }

    fn enabled(&self) -> bool {
        // Check if snapshot controller CSI is enabled along with either cinder or manila CSI
        // The snapshot controller only makes sense when at least one CSI driver is also enabled
        self.cluster.labels.snapshot_controller_csi_enabled &&
            (self.cluster.labels.cinder_csi_enabled || self.cluster.labels.manila_csi_enabled)
    }

    fn secret_name(&self) -> Result<String, ClusterError> {
        Ok(format!("{}-snapshot-controller-csi", self.cluster.stack_id()?))
    }

    fn manifests(&self) -> Result<BTreeMap<String, String>, helm::HelmTemplateError> {
        // Use the snapshot_controller_csi_tag from cluster labels
        let original_tag = &self.cluster.labels.snapshot_controller_csi_tag;

        // Get the appropriate embedded directory based on the tag
        // Prefer exact match first, then try prefix match, finally fall back to default v8.2.1
        let (manifest_dir, image_tag) = if let Some(dir) = MANIFEST_DIRS.get(original_tag.as_str()) {
            // Exact match found - use original tag
            (dir, original_tag.as_str())
        } else {
            // Try to match by major version prefix
            match original_tag.as_str() {
                s if s.starts_with("v4.") || s.starts_with("v4") ||
                   s.starts_with("v5.") || s.starts_with("v5") ||
                   s.starts_with("v6.") || s.starts_with("v6") ||
                   s.starts_with("v7.") || s.starts_with("v7") =>
                    // Use v7.0.2 for both manifests and image tag
                    (MANIFEST_DIRS.get("v7.0.2").unwrap(), "v7.0.2"),
                _ =>
                    // Default to v8.2.1 for both manifests and image tag
                    (MANIFEST_DIRS.get("v8.2.1").unwrap(), "v8.2.1"),
            }
        };

        let mut manifests = BTreeMap::new();

        // Initialize the manifests map with an order that ensures RBAC and CRDs are processed first
        // Add RBAC and CRD manifests from the embedded directory
        // These must be installed before any controllers or custom resources that use them
        let rbac_and_crd_files = vec![
            "rbac-snapshot-controller.yaml",
            "snapshot.storage.k8s.io_volumesnapshotclasses.yaml",
            "snapshot.storage.k8s.io_volumesnapshotcontents.yaml",
            "snapshot.storage.k8s.io_volumesnapshots.yaml",
        ];

        // Read RBAC and CRD files first to ensure proper installation order
        for file_name in &rbac_and_crd_files {
            let file = manifest_dir.get_file(file_name).ok_or_else(|| {
                helm::HelmTemplateError::HelmCommand(format!(
                    "Failed to read manifest file {}: File not found in embedded directory",
                    file_name
                ))
            })?;

            let content = file.contents_utf8().ok_or_else(|| {
                helm::HelmTemplateError::HelmCommand(format!(
                    "Failed to read manifest file {}: Invalid UTF-8 content",
                    file_name
                ))
            })?;

            manifests.insert(file_name.to_string(), content.to_string());
        }

        // Add the controller deployment
        let setup_snapshot_controller = self.generate_setup_snapshot_controller_manifest(image_tag);
        manifests.insert("setup-snapshot-controller.yaml".to_string(), setup_snapshot_controller);

        // Add the snapshot class manifests when respective CSI drivers are enabled
        // These depend on the CRDs being installed first
        if self.cluster.labels.cinder_csi_enabled {
            let cinder_snapshot_class = self.generate_cinder_snapshot_class_manifest();
            manifests.insert("cinder-snapshot-class.yaml".to_string(), cinder_snapshot_class);
        }

        if self.cluster.labels.manila_csi_enabled {
            let manila_snapshot_class = self.generate_manila_snapshot_class_manifest();
            manifests.insert("manila-snapshot-class.yaml".to_string(), manila_snapshot_class);
        }

        Ok(manifests)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_enabled() {
        // Test with snapshot and cinder CSI enabled
        let cluster_cinder = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(true)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_cinder = Addon::new(cluster_cinder.clone());
        assert!(addon_cinder.enabled(), "Should be enabled with snapshot and cinder CSI enabled");

        // Test with snapshot and manila CSI enabled
        let cluster_manila = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(false)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_manila = Addon::new(cluster_manila.clone());
        assert!(addon_manila.enabled(), "Should be enabled with snapshot and manila CSI enabled");

        // Test with all three enabled
        let cluster_all = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(true)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_all = Addon::new(cluster_all.clone());
        assert!(addon_all.enabled(), "Should be enabled with all three enabled");

        // Test with snapshot_controller_csi_enabled disabled
        let cluster_snapshot_disabled = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(false)
                .cinder_csi_enabled(true)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_snapshot_disabled = Addon::new(cluster_snapshot_disabled.clone());
        assert!(!addon_snapshot_disabled.enabled(), "Should be disabled when snapshot controller is disabled");

        // Test with both cinder and manila CSI disabled
        let cluster_no_csi = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(false)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_no_csi = Addon::new(cluster_no_csi.clone());
        assert!(!addon_no_csi.enabled(), "Should be disabled when both CSI drivers are disabled");

        // Test with all disabled
        let cluster_all_disabled = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(false)
                .cinder_csi_enabled(false)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_all_disabled = Addon::new(cluster_all_disabled.clone());
        assert!(!addon_all_disabled.enabled(), "Should be disabled when all are disabled");
    }

    #[test]
    fn test_manifests() {
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            // Default cluster with no CSI drivers enabled
            labels: magnum::ClusterLabels::builder().build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster.clone());
        let manifests = addon.manifests().expect("failed to get manifests");

        // Verify that all expected manifests are present
        assert!(manifests.contains_key("setup-snapshot-controller.yaml"));
        assert!(manifests.contains_key("rbac-snapshot-controller.yaml"));
        assert!(manifests.contains_key("snapshot.storage.k8s.io_volumesnapshotclasses.yaml"));
        assert!(manifests.contains_key("snapshot.storage.k8s.io_volumesnapshotcontents.yaml"));
        assert!(manifests.contains_key("snapshot.storage.k8s.io_volumesnapshots.yaml"));

        // Check that setup-snapshot-controller.yaml contains the default image tag
        let setup_manifest = manifests.get("setup-snapshot-controller.yaml").unwrap();
        assert!(setup_manifest.contains("image: registry.k8s.io/sig-storage/snapshot-controller:v8.2.1"));

        // Test with custom tag
        let cluster_custom_tag = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_tag("v7.0.2".to_string()) // Use exact tag that exists
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_custom_tag = Addon::new(cluster_custom_tag.clone());
        let manifests_custom = addon_custom_tag.manifests().expect("failed to get manifests with custom tag");

        // Verify that the setup manifest contains the custom tag
        let setup_manifest_custom = manifests_custom.get("setup-snapshot-controller.yaml").unwrap();
        assert!(setup_manifest_custom.contains("image: registry.k8s.io/sig-storage/snapshot-controller:v7.0.2"));

        // Test with various version prefixes that should map to v7.0.2
        let test_versions = vec!["v4.0.0", "v5", "v6.2", "v7.1.5"];

        for version in test_versions {
            let cluster_with_prefix = magnum::Cluster {
                uuid: "sample-uuid".to_string(),
                labels: magnum::ClusterLabels::builder()
                    .snapshot_controller_csi_tag(version.to_string())
                    .build(),
                stack_id: "kube-abcde".to_string().into(),
                cluster_template: magnum::ClusterTemplate {
                    network_driver: "cilium".to_string(),
                },
                ..Default::default()
            };

            let addon_with_prefix = Addon::new(cluster_with_prefix.clone());
            // This should succeed because our prefix matching should find v7.0.2 manifests
            let manifests_with_prefix = addon_with_prefix.manifests()
                .expect(&format!("failed to get manifests with prefix version {}", version));

            // Verify that the setup manifest uses v7.0.2 tag for older versions (not the requested version)
            let setup_manifest_with_prefix = manifests_with_prefix.get("setup-snapshot-controller.yaml").unwrap();

            // For v4, v5, v6 and v7 versions, image tag should always be v7.0.2
            assert!(setup_manifest_with_prefix.contains("image: registry.k8s.io/sig-storage/snapshot-controller:v7.0.2"),
                    "Image tag should be forced to v7.0.2 for {} version", version);

            // Ensure the tag that was requested is NOT in the manifest
            assert!(!setup_manifest_with_prefix.contains(&format!("image: registry.k8s.io/sig-storage/snapshot-controller:{}", version)),
                    "Original version tag {} should not be present in the manifest", version);

            // All manifests should come from v7.0.2 directory
            assert!(manifests_with_prefix.contains_key("rbac-snapshot-controller.yaml"),
                    "Should contain manifests from v7.0.2 directory");
        }

        // Test with custom tag and custom registry
        let cluster_custom_registry = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_tag("v7.0.2".to_string())
                .container_infra_prefix(Some("custom-registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_custom_registry = Addon::new(cluster_custom_registry.clone());
        let manifests_custom_registry = addon_custom_registry.manifests().expect("failed to get manifests with custom registry");

        // Verify that the setup manifest contains both custom tag and custom registry
        let setup_manifest_custom_registry = manifests_custom_registry.get("setup-snapshot-controller.yaml").unwrap();
        assert!(setup_manifest_custom_registry.contains("image: custom-registry.example.com/csi-snapshot-controller:v7.0.2"));
    }

    #[test]
    fn test_generate_setup_snapshot_controller_manifest() {
        // Test with default registry
        let cluster_default = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_default = Addon::new(cluster_default.clone());
        let manifest_default = addon_default.generate_setup_snapshot_controller_manifest("v8.2.1");

        // Check that the manifest contains the correct image path with default registry
        assert!(manifest_default.contains("image: registry.k8s.io/sig-storage/snapshot-controller:v8.2.1"));

        // Test with custom registry
        let cluster_custom = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .container_infra_prefix(Some("custom-registry.example.com".to_string()))
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_custom = Addon::new(cluster_custom.clone());
        let manifest_custom = addon_custom.generate_setup_snapshot_controller_manifest("v7.0.2");

        // Check that the manifest contains the correct image path with custom registry
        assert!(manifest_custom.contains("image: custom-registry.example.com/csi-snapshot-controller:v7.0.2"));

        // Test with custom registry and older version that should be forced to v7.0.2
        let manifest_custom_forced = addon_custom.generate_setup_snapshot_controller_manifest("v6.0.0");

        // Check that the manifest uses the provided tag with the custom registry
        assert!(manifest_custom_forced.contains("image: custom-registry.example.com/csi-snapshot-controller:v6.0.0"),
                "Should use the provided tag when explicitly calling generate_setup_snapshot_controller_manifest");
    }

    #[test]
    fn test_manifests_csi_drivers() {
        // Test with Cinder CSI enabled
        let cluster_cinder = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(true)
                .manila_csi_enabled(false)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_cinder = Addon::new(cluster_cinder.clone());
        let manifests_cinder = addon_cinder.manifests().expect("failed to get manifests with Cinder CSI enabled");

        // Verify that all expected manifests are present
        assert!(manifests_cinder.contains_key("setup-snapshot-controller.yaml"));
        assert!(manifests_cinder.contains_key("rbac-snapshot-controller.yaml"));
        assert!(manifests_cinder.contains_key("cinder-snapshot-class.yaml"),
               "Should include Cinder snapshot class manifest when Cinder CSI is enabled");
        assert!(!manifests_cinder.contains_key("manila-snapshot-class.yaml"),
               "Should not include Manila snapshot class manifest when Manila CSI is disabled");

        // Test with Manila CSI enabled
        let cluster_manila = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(false)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_manila = Addon::new(cluster_manila.clone());
        let manifests_manila = addon_manila.manifests().expect("failed to get manifests with Manila CSI enabled");

        // Verify that all expected manifests are present
        assert!(manifests_manila.contains_key("setup-snapshot-controller.yaml"));
        assert!(manifests_manila.contains_key("rbac-snapshot-controller.yaml"));
        assert!(!manifests_manila.contains_key("cinder-snapshot-class.yaml"),
               "Should not include Cinder snapshot class manifest when Cinder CSI is disabled");
        assert!(manifests_manila.contains_key("manila-snapshot-class.yaml"),
               "Should include Manila snapshot class manifest when Manila CSI is enabled");

        // Test with both Cinder and Manila CSI enabled
        let cluster_both = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .snapshot_controller_csi_enabled(true)
                .cinder_csi_enabled(true)
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon_both = Addon::new(cluster_both.clone());
        let manifests_both = addon_both.manifests().expect("failed to get manifests with both CSI drivers enabled");

        // Verify that all expected manifests are present
        assert!(manifests_both.contains_key("setup-snapshot-controller.yaml"));
        assert!(manifests_both.contains_key("rbac-snapshot-controller.yaml"));
        assert!(manifests_both.contains_key("cinder-snapshot-class.yaml"),
               "Should include Cinder snapshot class manifest when Cinder CSI is enabled");
        assert!(manifests_both.contains_key("manila-snapshot-class.yaml"),
               "Should include Manila snapshot class manifest when Manila CSI is enabled");
    }

    #[test]
    fn test_generate_cinder_snapshot_class_manifest() {
        // Create a basic cluster
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .cinder_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster.clone());
        let manifest = addon.generate_cinder_snapshot_class_manifest();

        // Verify the content of the Cinder snapshot class manifest
        assert!(manifest.contains("kind: VolumeSnapshotClass"));
        assert!(manifest.contains("name: block-snapshot"));
        assert!(manifest.contains("driver: cinder.csi.openstack.org"));
        assert!(manifest.contains("deletionPolicy: Delete"));
        assert!(manifest.contains("snapshot.storage.kubernetes.io/is-default-class: \"true\""));
    }

    #[test]
    fn test_generate_manila_snapshot_class_manifest() {
        // Create a basic cluster
        let cluster = magnum::Cluster {
            uuid: "sample-uuid".to_string(),
            labels: magnum::ClusterLabels::builder()
                .manila_csi_enabled(true)
                .build(),
            stack_id: "kube-abcde".to_string().into(),
            cluster_template: magnum::ClusterTemplate {
                network_driver: "cilium".to_string(),
            },
            ..Default::default()
        };

        let addon = Addon::new(cluster.clone());
        let manifest = addon.generate_manila_snapshot_class_manifest();

        // Verify the content of the Manila snapshot class manifest
        assert!(manifest.contains("kind: VolumeSnapshotClass"));
        assert!(manifest.contains("name: share-snapshot"));
        assert!(manifest.contains("driver: manila.csi.openstack.org"));
        assert!(manifest.contains("deletionPolicy: Delete"));
        assert!(manifest.contains("snapshot.storage.kubernetes.io/is-default-class: \"true\""));
    }
}
