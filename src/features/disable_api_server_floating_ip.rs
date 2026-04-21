use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources, ClusterClassVariables,
            ClusterClassVariablesSchema,
        },
        openstackclustertemplates::OpenStackClusterTemplate,
    },
    features::{
        ClusterClassVariablesSchemaExt, ClusterFeatureEntry, ClusterFeaturePatches,
        ClusterFeatureVariables,
    },
};
use cluster_feature_derive::ClusterFeatureValues;
use kube::CustomResourceExt;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
#[allow(dead_code)]
pub struct FeatureValues {
    #[serde(rename = "disableAPIServerFloatingIP")]
    pub disable_api_server_floating_ip: bool,

    /// Gates the `disableAPIServerFloatingIP` patch. Set to `true` when the
    /// user has asked to disable the API server floating IP, or — by the
    /// `immutable_fields` resolver — when the existing OpenStackCluster spec
    /// already has this field set.
    ///
    /// This prevents CAPO's immutability webhook from rejecting topology
    /// updates on clusters created by magnum-cluster-api versions prior to
    /// the introduction of the `enabledIf` guard (see PR #486), which had
    /// always patched this field on the spec.
    #[serde(rename = "disableAPIServerFloatingIPManaged")]
    pub disable_api_server_floating_ip_managed: bool,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "disableAPIServerFloatingIP".into(),
            enabled_if: Some(
                "{{ if .disableAPIServerFloatingIPManaged }}true{{end}}".into(),
            ),
            definitions: Some(vec![ClusterClassPatchesDefinitions {
                selector: ClusterClassPatchesDefinitionsSelector {
                    api_version: OpenStackClusterTemplate::api_resource().api_version,
                    kind: OpenStackClusterTemplate::api_resource().kind,
                    match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                        infrastructure_cluster: Some(true),
                        ..Default::default()
                    },
                },
                json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                    op: "add".into(),
                    path: "/spec/template/spec/disableAPIServerFloatingIP".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        variable: Some("disableAPIServerFloatingIP".into()),
                        ..Default::default()
                    }),
                    ..Default::default()
                }],
            }]),
            ..Default::default()
        }]
    }
}

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;
    use crate::resources::fixtures::default_values;
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_if_enabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.disable_api_server_floating_ip = true;
        values.disable_api_server_floating_ip_managed = true;

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .disable_api_server_floating_ip,
            Some(true)
        );
    }

    #[test]
    fn test_patches_if_disabled() {
        let feature = Feature {};

        let mut values = default_values();
        values.disable_api_server_floating_ip = false;
        values.disable_api_server_floating_ip_managed = false;

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .disable_api_server_floating_ip,
            None
        );
    }

    /// Regression: upgrades of clusters created by old magnum-cluster-api
    /// versions (pre-v0.25.x) that unconditionally patched
    /// `disableAPIServerFloatingIP: false` onto the spec. The
    /// `immutable_fields` resolver flips `disable_api_server_floating_ip_managed`
    /// to `true` so the patch still fires with the preserved `false` value,
    /// keeping the generated spec identical to the stored one and avoiding
    /// CAPO's immutability webhook.
    #[test]
    fn test_patches_if_managed_even_when_value_is_false() {
        let feature = Feature {};

        let mut values = default_values();
        values.disable_api_server_floating_ip = false;
        values.disable_api_server_floating_ip_managed = true;

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .disable_api_server_floating_ip,
            Some(false)
        );
    }
}
