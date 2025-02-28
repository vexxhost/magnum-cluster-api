use super::ClusterFeature;
use crate::{
    cluster_api::{
        clusterclasses::{
            ClusterClassPatches, ClusterClassPatchesDefinitions,
            ClusterClassPatchesDefinitionsJsonPatches,
            ClusterClassPatchesDefinitionsJsonPatchesValueFrom,
            ClusterClassPatchesDefinitionsSelector,
            ClusterClassPatchesDefinitionsSelectorMatchResources,
            ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass,
            ClusterClassVariables, ClusterClassVariablesSchema,
        },
        kubeadmconfigtemplates::{
            KubeadmConfigTemplate, KubeadmConfigTemplateTemplateSpecDiskSetupFilesystems,
            KubeadmConfigTemplateTemplateSpecDiskSetupPartitions,
        },
        kubeadmcontrolplanetemplates::{
            KubeadmControlPlaneTemplate,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems,
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions,
        },
        openstackmachinetemplates::OpenStackMachineTemplate,
    },
    features::{ClusterClassVariablesSchemaExt, ClusterFeatureEntry},
};
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "enableDockerVolume")]
pub struct EnableDockerVolumeConfig(pub bool);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "dockerVolumeSize")]
pub struct DockerVolumeSizeConfig(pub i64);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "dockerVolumeType")]
pub struct DockerVolumeTypeConfig(pub String);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "enableEtcdVolume")]
pub struct EnableEtcdVolumeConfig(pub bool);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "etcdVolumeSize")]
pub struct EtcdVolumeSizeConfig(pub i64);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "etcdVolumeType")]
pub struct EtcdVolumeTypeConfig(pub String);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
#[serde(rename = "availabilityZone")]
pub struct AvailabilityZoneConfig(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            ClusterClassVariables {
                name: "enableDockerVolume".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<EnableDockerVolumeConfig>(),
            },
            ClusterClassVariables {
                name: "dockerVolumeSize".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<DockerVolumeSizeConfig>(),
            },
            ClusterClassVariables {
                name: "dockerVolumeType".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<DockerVolumeTypeConfig>(),
            },
            ClusterClassVariables {
                name: "enableEtcdVolume".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<EnableEtcdVolumeConfig>(),
            },
            ClusterClassVariables {
                name: "etcdVolumeSize".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<EtcdVolumeSizeConfig>(),
            },
            ClusterClassVariables {
                name: "etcdVolumeType".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<EtcdVolumeTypeConfig>(),
            },
            ClusterClassVariables {
                name: "availabilityZone".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<AvailabilityZoneConfig>(),
            },
        ]
    }

    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "etcdVolume".into(),
                enabled_if: Some(r#"{{ if .enableEtcdVolume }}true{{ end }}"#.into()),
                definitions: Some(vec![
                    ClusterClassPatchesDefinitions {
                        selector: ClusterClassPatchesDefinitionsSelector {
                            api_version: OpenStackMachineTemplate::api_resource().api_version,
                            kind: OpenStackMachineTemplate::api_resource().kind,
                            match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                                control_plane: Some(true),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![ClusterClassPatchesDefinitionsJsonPatches {
                            op: "add".into(),
                            path: "/spec/template/spec/additionalBlockDevices/-".into(),
                            value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                template: Some(
                                    indoc!(
                                        r#"
                                        name: etcd
                                        sizeGiB: {{ .etcdVolumeSize }}
                                        storage:
                                            type: Volume
                                            volume:
                                                type: "{{ .etcdVolumeType }}"
                                                availabilityZone:
                                                  name: "{{ .availabilityZone }}"
                                        "#
                                    )
                                    .into(),
                                ),
                                ..Default::default()
                            }),
                            ..Default::default()
                        }],
                    },
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
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/partitions/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                                            device: "/dev/vdb".into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                                            device: "/dev/vdb".into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "etcd_disk".into(),
                                            ..Default::default()
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/mounts/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some("LABEL=etcd_disk".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/mounts/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some("/var/lib/etcd".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }
                        ],
                    },
                ]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "dockerVolume".into(),
                enabled_if: Some(r#"{{ if .enableDockerVolume }}true{{ end }}"#.into()),
                definitions: Some(vec![
                    ClusterClassPatchesDefinitions {
                        selector: ClusterClassPatchesDefinitionsSelector {
                            api_version: OpenStackMachineTemplate::api_resource().api_version,
                            kind: OpenStackMachineTemplate::api_resource().kind,
                            match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                                control_plane: Some(true),
                                machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                    names: Some(vec!["default-worker".to_string()])
                                }),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/additionalBlockDevices/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        indoc!(
                                            r#"
                                            name: docker
                                            sizeGiB: {{ .dockerVolumeSize }}
                                            storage:
                                                type: Volume
                                                volume:
                                                    type: "{{ .dockerVolumeType }}"
                                                    availabilityZone:
                                                      name: "{{ .availabilityZone }}"
                                            "#
                                        )
                                        .into(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }
                        ],
                    },
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
                                path: "/spec/template/spec/kubeadmConfigSpec/mounts/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some("LABEL=docker_disk".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/mounts/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some("/var/lib/containerd".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            }
                        ],
                    },
                    ClusterClassPatchesDefinitions {
                        selector: ClusterClassPatchesDefinitionsSelector {
                            api_version: KubeadmConfigTemplate::api_resource().api_version,
                            kind: KubeadmConfigTemplate::api_resource().kind,
                            match_resources: ClusterClassPatchesDefinitionsSelectorMatchResources {
                                machine_deployment_class: Some(ClusterClassPatchesDefinitionsSelectorMatchResourcesMachineDeploymentClass {
                                    names: Some(vec!["default-worker".to_string()])
                                }),
                                ..Default::default()
                            },
                        },
                        json_patches: vec![
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/mounts/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some("LABEL=docker_disk".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/mounts/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some("/var/lib/containerd".into()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/diskSetup/partitions/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmConfigTemplateTemplateSpecDiskSetupPartitions {
                                            device: "/dev/vdb".into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmConfigTemplateTemplateSpecDiskSetupFilesystems {
                                            device: "/dev/vdb".into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "docker_disk".into(),
                                            ..Default::default()
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                        ],
                    }
                ]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "etcdAndDockerVolumeForControlPlane".into(),
                enabled_if: Some(r#"{{ if and .enableEtcdVolume .enableDockerVolume }}true{{ end }}"#.into()),
                definitions: Some(vec![
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
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/partitions/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                                            device: "/dev/vdc".into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                                            device: "/dev/vdc".into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "docker_disk".into(),
                                            ..Default::default()
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                        ],
                    },
                ]),
                ..Default::default()
            },
            ClusterClassPatches {
                name: "onlyDockerVolumeForControlPlane".into(),
                enabled_if: Some(r#"{{ if and .enableDockerVolume (not .enableEtcdVolume) }}true{{ end }}"#.into()),
                definitions: Some(vec![
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
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/partitions/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                                            device: "/dev/vdb".into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(serde_yaml::to_string(
                                        &KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                                            device: "/dev/vdb".into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "docker_disk".into(),
                                            ..Default::default()
                                        }
                                    ).unwrap()),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                        ],
                    },
                ]),
                ..Default::default()
            }
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
        cluster_api::{
            kubeadmconfigtemplates::KubeadmConfigTemplateTemplateSpecDiskSetup,
            kubeadmcontrolplanetemplates::KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetup,
            openstackmachinetemplates::{
                OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices,
                OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage,
                OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume,
                OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone,
            },
        },
        features::test::{default_values, TestClusterResources}
    };
    use pretty_assertions::assert_eq;

    #[test]
    fn test_patches_with_no_volumes() {
        let feature = Feature {};

        let values = default_values();
        let patches = feature.patches();

        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);
    }

    #[test]
    fn test_patches_with_etcd_volumes_only() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_etcd_volume = EnableEtcdVolumeConfig(true);
        values.etcd_volume_size = EtcdVolumeSizeConfig(80);
        values.etcd_volume_type = EtcdVolumeTypeConfig("nvme".into());

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .control_plane_openstack_machine_template
                .spec
                .template
                .spec
                .additional_block_devices
                .expect("additional block devices should be set"),
                vec![OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                    name: "etcd".into(),
                    size_gi_b: values.etcd_volume_size.0,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.etcd_volume_type.0),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.availability_zone.0),
                                ..Default::default()
                            })
                        })
                    }
                }]
        );

        assert_eq!(
            resources
                .worker_openstack_machine_template
                .spec
                .template
                .spec
                .additional_block_devices
                .expect("additional block devices should be set"),
            vec![]
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .disk_setup
                .expect("disk setup should be set"),
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetup {
                partitions: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                        device: "/dev/vdb".into(),
                        layout: true,
                        overwrite: Some(false),
                        table_type: Some("gpt".into()),
                    }
                ]),
                filesystems: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                        device: "/dev/vdb".into(),
                        extra_opts: Some(vec![
                            "-F".into(),
                            "-E".into(),
                            "lazy_itable_init=1,lazy_journal_init=1".into(),
                        ]),
                        filesystem: "ext4".into(),
                        label: "etcd_disk".into(),
                        ..Default::default()
                    }
                ])
            }
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .mounts
                .expect("mounts should be set"),
            vec!["LABEL=etcd_disk".to_string(), "/var/lib/etcd".to_string()]
        );

        let kct_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("kubeadm config spec should be set");

        assert_eq!(
            kct_spec
                .clone()
                .disk_setup
                .expect("disk setup should be set"),
            KubeadmConfigTemplateTemplateSpecDiskSetup {
                partitions: Some(vec![]),
                filesystems: Some(vec![])
            }
        );

        assert_eq!(
            kct_spec.clone().mounts.expect("mounts should be set"),
            Vec::<String>::new()
        );
    }

    #[test]
    fn test_patches_with_docker_volumes_only() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_docker_volume = EnableDockerVolumeConfig(true);
        values.docker_volume_size = DockerVolumeSizeConfig(160);
        values.docker_volume_type = DockerVolumeTypeConfig("ssd".into());

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .control_plane_openstack_machine_template
                .spec
                .template
                .spec
                .additional_block_devices
                .expect("additional block devices should be set"),
                vec![OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                    name: "docker".into(),
                    size_gi_b: values.clone().docker_volume_size.0,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type.0),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone.0),
                                ..Default::default()
                            })
                        })
                    }
                }]
        );

        assert_eq!(
            resources
                .worker_openstack_machine_template
                .spec
                .template
                .spec
                .additional_block_devices
                .expect("additional block devices should be set"),
                vec![OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                    name: "docker".into(),
                    size_gi_b: values.clone().docker_volume_size.0,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type.0),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone.0),
                                ..Default::default()
                            })
                        })
                    }
                }]
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .disk_setup
                .expect("disk setup should be set"),
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetup {
                partitions: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                        device: "/dev/vdb".into(),
                        layout: true,
                        overwrite: Some(false),
                        table_type: Some("gpt".into()),
                    }
                ]),
                filesystems: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                        device: "/dev/vdb".into(),
                        extra_opts: Some(vec![
                            "-F".into(),
                            "-E".into(),
                            "lazy_itable_init=1,lazy_journal_init=1".into(),
                        ]),
                        filesystem: "ext4".into(),
                        label: "docker_disk".into(),
                        ..Default::default()
                    }
                ])
            }
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .mounts
                .expect("mounts should be set"),
            vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]
        );

        let kct_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("kubeadm config spec should be set");

        assert_eq!(
            kct_spec
                .clone()
                .disk_setup
                .expect("disk setup should be set"),
            KubeadmConfigTemplateTemplateSpecDiskSetup {
                partitions: Some(vec![KubeadmConfigTemplateTemplateSpecDiskSetupPartitions {
                    device: "/dev/vdb".into(),
                    layout: true,
                    overwrite: Some(false),
                    table_type: Some("gpt".into()),
                }]),
                filesystems: Some(vec![
                    KubeadmConfigTemplateTemplateSpecDiskSetupFilesystems {
                        device: "/dev/vdb".into(),
                        extra_opts: Some(vec![
                            "-F".into(),
                            "-E".into(),
                            "lazy_itable_init=1,lazy_journal_init=1".into(),
                        ]),
                        filesystem: "ext4".into(),
                        label: "docker_disk".into(),
                        ..Default::default()
                    }
                ])
            }
        );

        assert_eq!(
            kct_spec.clone().mounts.expect("mounts should be set"),
            vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]
        );
    }

    #[test]
    fn test_patches_with_etcd_and_docker_volumes() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_etcd_volume = EnableEtcdVolumeConfig(true);
        values.etcd_volume_size = EtcdVolumeSizeConfig(80);
        values.etcd_volume_type = EtcdVolumeTypeConfig("nvme".into());
        values.enable_docker_volume = EnableDockerVolumeConfig(true);
        values.docker_volume_size = DockerVolumeSizeConfig(160);
        values.docker_volume_type = DockerVolumeTypeConfig("ssd".into());

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);

        assert_eq!(
            resources
                .control_plane_openstack_machine_template
                .spec
                .template
                .spec
                .additional_block_devices
                .expect("additional block devices should be set"),
                vec![
                    OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                        name: "etcd".into(),
                        size_gi_b: values.clone().etcd_volume_size.0,
                        storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                            r#type: "Volume".into(),
                            volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                                r#type: Some(values.clone().etcd_volume_type.0),
                                availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                    name: Some(values.clone().availability_zone.0),
                                    ..Default::default()
                                })
                            })
                        }
                    },
                    OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                        name: "docker".into(),
                        size_gi_b: values.clone().docker_volume_size.0,
                        storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                            r#type: "Volume".into(),
                            volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                                r#type: Some(values.clone().docker_volume_type.0),
                                availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                    name: Some(values.clone().availability_zone.0),
                                    ..Default::default()
                                })
                            })
                        }
                    }
                ]
        );

        assert_eq!(
            resources
                .worker_openstack_machine_template
                .spec
                .template
                .spec
                .additional_block_devices
                .expect("additional block devices should be set"),
                vec![OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                    name: "docker".into(),
                    size_gi_b: values.docker_volume_size.0,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type.0),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone.0),
                                ..Default::default()
                            })
                        })
                    }
                }]
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .disk_setup
                .expect("disk setup should be set"),
            KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetup {
                partitions: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                        device: "/dev/vdb".into(),
                        layout: true,
                        overwrite: Some(false),
                        table_type: Some("gpt".into()),
                    },
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                        device: "/dev/vdc".into(),
                        layout: true,
                        overwrite: Some(false),
                        table_type: Some("gpt".into()),
                    }
                ]),
                filesystems: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                        device: "/dev/vdb".into(),
                        extra_opts: Some(vec![
                            "-F".into(),
                            "-E".into(),
                            "lazy_itable_init=1,lazy_journal_init=1".into(),
                        ]),
                        filesystem: "ext4".into(),
                        label: "etcd_disk".into(),
                        ..Default::default()
                    },
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                        device: "/dev/vdc".into(),
                        extra_opts: Some(vec![
                            "-F".into(),
                            "-E".into(),
                            "lazy_itable_init=1,lazy_journal_init=1".into(),
                        ]),
                        filesystem: "ext4".into(),
                        label: "docker_disk".into(),
                        ..Default::default()
                    }
                ])
            }
        );

        assert_eq!(
            resources
                .kubeadm_control_plane_template
                .spec
                .template
                .spec
                .kubeadm_config_spec
                .mounts
                .expect("mounts should be set"),
            vec![
                "LABEL=etcd_disk".to_string(),
                "/var/lib/etcd".to_string(),
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]
        );

        let kct_spec = resources
            .kubeadm_config_template
            .spec
            .template
            .spec
            .expect("kubeadm config spec should be set");

        assert_eq!(
            kct_spec
                .clone()
                .disk_setup
                .expect("disk setup should be set"),
            KubeadmConfigTemplateTemplateSpecDiskSetup {
                partitions: Some(vec![KubeadmConfigTemplateTemplateSpecDiskSetupPartitions {
                    device: "/dev/vdb".into(),
                    layout: true,
                    overwrite: Some(false),
                    table_type: Some("gpt".into()),
                }]),
                filesystems: Some(vec![
                    KubeadmConfigTemplateTemplateSpecDiskSetupFilesystems {
                        device: "/dev/vdb".into(),
                        extra_opts: Some(vec![
                            "-F".into(),
                            "-E".into(),
                            "lazy_itable_init=1,lazy_journal_init=1".into(),
                        ]),
                        filesystem: "ext4".into(),
                        label: "docker_disk".into(),
                        ..Default::default()
                    }
                ])
            }
        );

        assert_eq!(
            kct_spec.clone().mounts.expect("mounts should be set"),
            vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]
        );
    }
}
