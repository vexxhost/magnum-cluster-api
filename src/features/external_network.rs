use super::ClusterFeature;
use crate::{
    cluster_api::{
        openstackclustertemplates::{
            OpenStackClusterTemplate, OpenStackClusterTemplateTemplateSpecExternalNetwork,
        },
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::ClusterClassVariablesSchemaExt,
};
use cluster_api_rs::capi_clusterclass::{
    ClusterClassPatches, ClusterClassPatchesDefinitions, ClusterClassPatchesDefinitionsJsonPatches,
    ClusterClassPatchesDefinitionsJsonPatchesValueFrom, ClusterClassPatchesDefinitionsSelector,
    ClusterClassPatchesDefinitionsSelectorMatchResources,
    ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
    ClusterClassVariables, ClusterClassVariablesSchema,
};
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[schemars(with = "string")]
pub struct Config(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![ClusterClassVariables {
            name: "externalNetworkId".into(),
            metadata: None,
            required: true,
            schema: ClusterClassVariablesSchema::from_object::<Config>(),
        }]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![ClusterClassPatches {
            name: "externalNetworkId".into(),
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
                    path: "/spec/template/spec/externalNetwork".into(),
                    value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                        template: Some(
                            serde_yaml::to_string(
                                &OpenStackClusterTemplateTemplateSpecExternalNetwork {
                                    id: Some("{{ .externalNetworkId }}".into()),
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
        }]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::features::test::TestClusterResources;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "externalNetworkId")]
        external_network_id: Config,
    }

    #[test]
    fn test_patches() {
        let feature = Feature {};
        let values = Values {
            external_network_id: Config("external-network-id".into()),
        };

        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .openstack_cluster_template
                .spec
                .template
                .spec
                .external_network
                .expect("external network should be set")
                .id,
            Some(values.external_network_id.clone().0)
        );
    }
}
