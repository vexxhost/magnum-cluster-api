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
        openstackclustertemplates::{
            OpenStackClusterTemplate, OpenStackClusterTemplateTemplateSpecNetwork,
            OpenStackClusterTemplateTemplateSpecSubnets,
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

#[derive(Serialize, Deserialize, ClusterFeatureValues)]
pub struct FeatureValues {
    #[serde(rename = "nodeCidr")]
    pub node_cidr: String,

    #[serde(rename = "dnsNameservers")]
    pub dns_nameservers: Vec<String>,

    #[serde(rename = "fixedNetworkId")]
    pub fixed_network_id: String,

    #[serde(rename = "fixedSubnetId")]
    pub fixed_subnet_id: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "newNetworkConfig".into(),
                enabled_if: Some(r#"{{ if eq .fixedNetworkId "" }}true{{end}}"#.into()),
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
                        path: "/spec/template/spec/managedSubnets".into(),
                        value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                            template: Some(
                                indoc!(
                                    r#"
                                    - cidr: {{ .nodeCidr }}
                                      dnsNameservers:
                                      {{- range .dnsNameservers }}
                                        - {{ . }}
                                      {{- end }}
                                    "#
                                )
                                .into(),
                            ),
                            ..Default::default()
                        }),
                        ..Default::default()
                    }],
                }]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "existingFixedNetworkIdConfig".into(),
                enabled_if: Some(r#"{{ if ne .fixedNetworkId "" }}true{{end}}"#.into()),
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
                        path: "/spec/template/spec/network".into(),
                        value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                            template: Some(
                                serde_yaml::to_string(
                                    &OpenStackClusterTemplateTemplateSpecNetwork {
                                        id: Some("{{ .fixedNetworkId }}".to_string()),
                                        ..Default::default()
                                    },
                                )
                                .unwrap(),
                            ),
                            ..Default::default()
                        }),
                        ..Default::default()
                    }],
                }]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "existingFixedSubnetIdConfig".into(),
                enabled_if: Some(r#"{{ if ne .fixedSubnetId "" }}true{{end}}"#.into()),
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
                        path: "/spec/template/spec/subnets".into(),
                        value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                            template: Some(
                                serde_yaml::to_string(&vec![
                                    OpenStackClusterTemplateTemplateSpecSubnets {
                                        id: Some("{{ .fixedSubnetId }}".to_string()),
                                        ..Default::default()
                                    },
                                ])
                                .unwrap(),
                            ),
                            ..Default::default()
                        }),
                        ..Default::default()
                    }],
                }]),
                ..Default::default()
            },
        ]
    }
}

inventory::submit! {
    ClusterFeatureEntry{ feature: &Feature {} }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cluster_api::openstackclustertemplates::OpenStackClusterTemplateTemplateSpecManagedSubnets,
        features::test::TestClusterResources, resources::fixtures::default_values,
    };
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_for_new_network() {
        let feature = Feature {};

        let mut values = default_values();
        values.node_cidr = "10.0.0.0/24".into();
        values.dns_nameservers = vec!["1.1.1.1".into(), "1.0.0.1".into()];
        values.fixed_network_id = "".into();
        values.fixed_subnet_id = "".into();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .managed_subnets
                .expect("managed subnets should be set"),
            vec![OpenStackClusterTemplateTemplateSpecManagedSubnets {
                cidr: values.node_cidr,
                dns_nameservers: Some(values.dns_nameservers),
                ..Default::default()
            }]
        );
    }

    #[test]
    fn test_patches_for_existing_network() {
        let feature = Feature {};

        let mut values = default_values();
        values.node_cidr = "10.0.0.0/24".into();
        values.dns_nameservers = vec!["1.1.1.1".into(), "1.0.0.1".into()];
        values.fixed_network_id = "e3172714-4ac5-4152-abf7-2d37387977e7".into();
        values.fixed_subnet_id = "".into();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .network
                .expect("network should be set"),
            OpenStackClusterTemplateTemplateSpecNetwork {
                id: Some(values.fixed_network_id),
                ..Default::default()
            }
        );
    }

    #[test]
    fn test_patches_for_existing_network_and_subnet() {
        let feature = Feature {};

        let mut values = default_values();
        values.node_cidr = "10.0.0.0/24".into();
        values.dns_nameservers = vec!["1.1.1.1".into(), "1.0.0.1".into()];
        values.fixed_network_id = "e3172714-4ac5-4152-abf7-2d37387977e7".into();
        values.fixed_subnet_id = "5ef0bdfa-c836-4753-ae38-d2ca71ef921a".into();

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .network
                .expect("network should be set"),
            OpenStackClusterTemplateTemplateSpecNetwork {
                id: Some(values.fixed_network_id),
                ..Default::default()
            }
        );

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .subnets
                .expect("subnets should be set"),
            vec![OpenStackClusterTemplateTemplateSpecSubnets {
                id: Some(values.fixed_subnet_id),
                ..Default::default()
            }]
        );
    }
}
