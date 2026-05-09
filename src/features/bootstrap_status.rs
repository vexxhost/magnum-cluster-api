//! Explicit cloud-init bootstrap-success sentinel + error-log capture.
//!
//! ## Background
//!
//! CAPI's bootstrap protocol exposes `/run/cluster-api/bootstrap-success.complete`
//! and `/run/cluster-api/bootstrap-error.log` as the canonical signals
//! that bootstrap finished. The kubeadm bootstrap provider already
//! emits a `runcmd:` line that writes the success sentinel after
//! `kubeadm init` succeeds — but that line runs BEFORE any operator-
//! supplied `extra_post_kubeadm_commands` (and before any other
//! mcapi feature's postKubeadm patches), so a failure in those
//! commands is never reflected in either sentinel.
//!
//! Trying to wrap the runcmd block with `set -e` + `trap '...' EXIT`
//! does not work either: each `runcmd:` list entry is executed by
//! cloud-init in its own `/bin/sh -c <string>` subshell, so shell
//! options and traps installed in entry N do not propagate to entry
//! N+1. (This was the bug in the previous revision of this feature —
//! it relied on a `bash -c` wrapped trap that fired only on its own
//! sub-shell exit, with rc=0.)
//!
//! ## What this feature does
//!
//! Installs a small systemd oneshot unit, `mcapi-bootstrap-status.service`,
//! that runs once after `cloud-final.service` finishes (success or
//! failure) and writes the canonical CAPI bootstrap signals based on
//! cloud-init's own status. Since cloud-final.service is what runs
//! the runcmd block — including kubeadm init AND any user-supplied
//! `extra_post_kubeadm_commands` — by the time our unit fires, all
//! bootstrap activity is finished.
//!
//! The flow:
//!
//! 1. **`files`** writes two artefacts on disk before runcmd starts:
//!    - `/usr/local/sbin/mcapi-bootstrap-status` — a tiny POSIX-sh
//!      script that runs `cloud-init status --wait` (which blocks
//!      until cloud-init reaches a final state and exits non-zero on
//!      any "degraded done" or "error" status), then writes either
//!      `/run/cluster-api/bootstrap-success.complete` (clean exit) or
//!      `/run/cluster-api/bootstrap-error.log` (non-zero exit, with
//!      the last 200 lines of `/var/log/cloud-init-output.log`).
//!      In the failure branch it ALSO removes any stale
//!      `bootstrap-success.complete` previously written by the
//!      kubeadm bootstrap provider, so a post-kubeadm failure
//!      correctly invalidates the success signal.
//!    - `/etc/systemd/system/mcapi-bootstrap-status.service` — a
//!      `Type=oneshot` unit ordered `After=cloud-final.service`,
//!      `WantedBy=multi-user.target`. `Wants=cloud-final.service`
//!      (rather than `Requires=`) so a degraded cloud-final does not
//!      block our reporter.
//!
//! 2. **`preKubeadmCommands`** prepends a single line that runs
//!    BEFORE all other mcapi/upstream pre-kubeadm entries:
//!    `systemctl daemon-reload && systemctl enable
//!    mcapi-bootstrap-status.service`. This makes systemd notice the
//!    new unit and queue it for the in-flight `multi-user.target`
//!    transaction. The unit then fires once cloud-final exits.
//!    Because the line is the FIRST preKubeadm entry, even if all
//!    later entries (kubeadm init, post-kubeadm, etc.) fail, the
//!    reporter is still enabled and will fire.
//!
//! ## What this feature deliberately does NOT do
//!
//! - It does NOT change the node's "Ready" status from the cluster's
//!   point of view. If kubeadm succeeded and the kubelet joined, the
//!   Machine still reaches `Ready=True` and the cluster still reaches
//!   `CREATE_COMPLETE` — that is by design (kubelet IS up, the
//!   cluster IS technically usable). The feature's value is making
//!   `extra_post_kubeadm_commands` failures **observable**: the
//!   error-log file is surfaced by CAPI as a `BootstrapReady=False,
//!   Reason=BootstrapFailed` condition, which the driver-side
//!   Machine.Status.Conditions aggregator surfaces in
//!   `openstack coe cluster show -c status_reason`. Without this
//!   feature, post-kubeadm failures are completely silent unless an
//!   operator SSHes into the node.
//! - **Layer 2** (ship the error log into a ConfigMap on the
//!   management cluster) requires kubectl on the failing node + an
//!   injected kubeconfig that survives bootstrap failure. Out of
//!   scope.
//!
//! ## References
//!
//! - CAPI bootstrap protocol contract for
//!   `/run/cluster-api/bootstrap-{success.complete,error.log}`.

use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources,
            ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
            ClusterClassVariables, ClusterClassVariablesSchema,
        },
        kubeadmconfigtemplates::{KubeadmConfigTemplate, KubeadmConfigTemplateTemplateSpecFiles},
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles,
        },
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use indoc::indoc;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    /// Always-on. Surfaces as a no-op variable so the ClusterClass schema
    /// exposes a stable knob if we later want to gate this trailer behind
    /// an opt-out label (e.g. for integration tests that intentionally
    /// run with broken bootstrap to assert the failure surface).
    #[serde(rename = "bootstrapStatusEnabled")]
    pub bootstrap_status_enabled: bool,
}

const STATUS_SCRIPT_PATH: &str = "/usr/local/sbin/mcapi-bootstrap-status";
const STATUS_UNIT_PATH: &str = "/etc/systemd/system/mcapi-bootstrap-status.service";

const STATUS_SCRIPT: &str = indoc!(
    r#"
    #!/bin/sh
    # Runs once, oneshot, after cloud-final.service.
    #
    # cloud-init status --wait blocks until cloud-init has reached a
    # final state. Exit codes:
    #   0  done           - everything succeeded
    #   1  not run        - module did not run (treat as error)
    #   2  degraded done  - cloud-init finished but at least one module
    #                       (typically runcmd) reported a recoverable
    #                       error. This is the path hit when any
    #                       runcmd entry — including operator
    #                       extra_post_kubeadm_commands — exits non-zero.
    #   3  error          - fatal cloud-init failure
    set +e
    mkdir -p /run/cluster-api
    cloud-init status --wait
    rc=$?
    if [ "$rc" -eq 0 ]; then
        touch /run/cluster-api/bootstrap-success.complete
    else
        rm -f /run/cluster-api/bootstrap-success.complete
        tail -n 200 /var/log/cloud-init-output.log \
            > /run/cluster-api/bootstrap-error.log 2>&1 || true
    fi
    exit 0
    "#
);

const STATUS_UNIT: &str = indoc!(
    r#"
    [Unit]
    Description=mcapi bootstrap status reporter
    After=cloud-final.service
    Wants=cloud-final.service

    [Service]
    Type=oneshot
    ExecStart=/usr/local/sbin/mcapi-bootstrap-status
    RemainAfterExit=yes

    [Install]
    WantedBy=multi-user.target
    "#
);

const ENABLE_UNIT: &str =
    "systemctl daemon-reload && systemctl enable mcapi-bootstrap-status.service && systemctl start --no-block mcapi-bootstrap-status.service";

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "bootstrapStatus".into(),
            enabled_if: Some("{{ if .bootstrapStatusEnabled }}true{{end}}".into()),
            definitions: Some(vec![
                // Control-plane bootstrap.
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: KubeadmControlPlaneTemplate::api_resource().api_version,
                        kind: KubeadmControlPlaneTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            control_plane: Some(true),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                            value: Some(json!(
                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                    path: STATUS_SCRIPT_PATH.into(),
                                    permissions: Some("0755".into()),
                                    owner: Some("root:root".into()),
                                    content: Some(STATUS_SCRIPT.into()),
                                    ..Default::default()
                                }
                            )),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/files/-".into(),
                            value: Some(json!(
                                KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecFiles {
                                    path: STATUS_UNIT_PATH.into(),
                                    permissions: Some("0644".into()),
                                    owner: Some("root:root".into()),
                                    content: Some(STATUS_UNIT.into()),
                                    ..Default::default()
                                }
                            )),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/kubeadmConfigSpec/preKubeadmCommands/0"
                                .into(),
                            value: Some(ENABLE_UNIT.into()),
                            ..Default::default()
                        },
                    ],
                },
                // Worker bootstrap.
                ClusterClassPatchesDefinitions {
                    selector: ClusterClassPatchesDefinitionsSelector {
                        api_version: KubeadmConfigTemplate::api_resource().api_version,
                        kind: KubeadmConfigTemplate::api_resource().kind,
                        match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                            machine_deployment_class: Some(
                                ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                    names: Some(vec!["default-worker".to_string()]),
                                },
                            ),
                            ..Default::default()
                        },
                    },
                    json_patches: vec![
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/files/-".into(),
                            value: Some(json!(KubeadmConfigTemplateTemplateSpecFiles {
                                path: STATUS_SCRIPT_PATH.into(),
                                permissions: Some("0755".into()),
                                owner: Some("root:root".into()),
                                content: Some(STATUS_SCRIPT.into()),
                                ..Default::default()
                            })),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/files/-".into(),
                            value: Some(json!(KubeadmConfigTemplateTemplateSpecFiles {
                                path: STATUS_UNIT_PATH.into(),
                                permissions: Some("0644".into()),
                                owner: Some("root:root".into()),
                                content: Some(STATUS_UNIT.into()),
                                ..Default::default()
                            })),
                            ..Default::default()
                        },
                        ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/preKubeadmCommands/0".into(),
                            value: Some(ENABLE_UNIT.into()),
                            ..Default::default()
                        },
                    ],
                },
            ]),
            ..Default::default()
        }]
    }
}

inventory::submit! {
    ClusterFeatureEntry { feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_emit_unit_and_enable_on_control_plane() {
        let feature = Feature {};

        let mut values = default_values();
        values.bootstrap_status_enabled = true;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let cp_spec = &resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec;

        // The two files should have been added.
        let files = cp_spec
            .files
            .as_ref()
            .expect("kubeadmConfigSpec.files should be set");
        let script = files
            .iter()
            .find(|f| f.path == STATUS_SCRIPT_PATH)
            .expect("status script file not added");
        assert_eq!(script.permissions.as_deref(), Some("0755"));
        let script_content = script.content.as_deref().unwrap_or("");
        assert!(
            script_content.contains("cloud-init status --wait"),
            "script should call `cloud-init status --wait`: {script_content}"
        );
        assert!(
            script_content.contains("bootstrap-success.complete"),
            "script should write the success sentinel: {script_content}"
        );
        assert!(
            script_content.contains("bootstrap-error.log"),
            "script should write the error log: {script_content}"
        );
        assert!(
            script_content.contains("rm -f /run/cluster-api/bootstrap-success.complete"),
            "script should remove stale success sentinel on failure: {script_content}"
        );

        let unit = files
            .iter()
            .find(|f| f.path == STATUS_UNIT_PATH)
            .expect("status unit file not added");
        let unit_content = unit.content.as_deref().unwrap_or("");
        assert!(
            unit_content.contains("After=cloud-final.service"),
            "unit must run after cloud-final: {unit_content}"
        );
        assert!(
            unit_content.contains("Type=oneshot"),
            "unit must be oneshot: {unit_content}"
        );
        assert!(
            unit_content.contains("WantedBy=multi-user.target"),
            "unit must be enabled into multi-user.target: {unit_content}"
        );

        // The enable line must be FIRST in preKubeadmCommands so that
        // even if every later runcmd entry fails, the reporter is
        // already enabled and will fire after cloud-final exits.
        let pre = cp_spec
            .pre_kubeadm_commands
            .as_ref()
            .expect("preKubeadmCommands should exist");
        assert_eq!(
            pre.first().map(|s| s.as_str()),
            Some(ENABLE_UNIT),
            "enable line must be the FIRST preKubeadm entry; got {:?}",
            pre
        );
    }

    #[test]
    fn test_patches_emit_unit_and_enable_on_workers() {
        let feature = Feature {};

        let mut values = default_values();
        values.bootstrap_status_enabled = true;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        let worker_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .as_ref()
            .expect("worker spec should be set");

        let files = worker_spec
            .files
            .as_ref()
            .expect("worker files should be set");
        assert!(files.iter().any(|f| f.path == STATUS_SCRIPT_PATH));
        assert!(files.iter().any(|f| f.path == STATUS_UNIT_PATH));

        let pre = worker_spec
            .pre_kubeadm_commands
            .as_ref()
            .expect("worker preKubeadmCommands should exist");
        assert_eq!(
            pre.first().map(|s| s.as_str()),
            Some(ENABLE_UNIT),
            "worker enable line must be the FIRST preKubeadm entry"
        );
    }

    #[test]
    fn test_no_patches_when_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.bootstrap_status_enabled = false;

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        // When the gate is off, neither the CP nor worker spec should
        // have the unit/script files or the enable line.
        let cp_files = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .files
            .clone()
            .unwrap_or_default();
        assert_eq!(
            cp_files
                .iter()
                .filter(|f| f.path == STATUS_SCRIPT_PATH || f.path == STATUS_UNIT_PATH)
                .count(),
            0
        );
        let cp_pre = resources
            .kubeadm_control_plane_template
            .spec
            .template
            .spec
            .kubeadm_config_spec
            .pre_kubeadm_commands
            .clone()
            .unwrap_or_default();
        assert_eq!(
            cp_pre.iter().filter(|c| *c == ENABLE_UNIT).count(),
            0
        );
    }
}
