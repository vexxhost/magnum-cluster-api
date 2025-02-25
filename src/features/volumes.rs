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
    features::ClusterClassVariablesSchemaExt,
};
use indoc::indoc;
use kube::CustomResourceExt;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
pub struct EnableVolumeConfig(pub bool);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
pub struct VolumeSizeConfig(pub i64);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
pub struct VolumeTypeConfig(pub String);

#[derive(Clone, Serialize, Deserialize, JsonSchema)]
#[serde(transparent)]
pub struct AvailabilityZoneConfig(pub String);

pub struct Feature {}

impl ClusterFeature for Feature {
    fn variables(&self) -> Vec<ClusterClassVariables> {
        vec![
            ClusterClassVariables {
                name: "enableDockerVolume".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<EnableVolumeConfig>(),
            },
            ClusterClassVariables {
                name: "dockerVolumeSize".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<VolumeSizeConfig>(),
            },
            ClusterClassVariables {
                name: "dockerVolumeType".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<VolumeTypeConfig>(),
            },
            ClusterClassVariables {
                name: "enableEtcdVolume".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<EnableVolumeConfig>(),
            },
            ClusterClassVariables {
                name: "etcdVolumeSize".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<VolumeSizeConfig>(),
            },
            ClusterClassVariables {
                name: "etcdVolumeType".into(),
                metadata: None,
                required: true,
                schema: ClusterClassVariablesSchema::from_object::<VolumeTypeConfig>(),
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
        features::test::TestClusterResources,
    };
    use pretty_assertions::assert_eq;

    #[derive(Clone, Serialize, Deserialize)]
    pub struct Values {
        #[serde(rename = "enableDockerVolume")]
        enable_docker_volume: EnableVolumeConfig,

        #[serde(rename = "dockerVolumeSize")]
        docker_volume_size: VolumeSizeConfig,

        #[serde(rename = "dockerVolumeType")]
        docker_volume_type: VolumeTypeConfig,

        #[serde(rename = "enableEtcdVolume")]
        enable_etcd_volume: EnableVolumeConfig,

        #[serde(rename = "etcdVolumeSize")]
        etcd_volume_size: VolumeSizeConfig,

        #[serde(rename = "etcdVolumeType")]
        etcd_volume_type: VolumeTypeConfig,

        #[serde(rename = "availabilityZone")]
        availability_zone: AvailabilityZoneConfig,
    }

    #[test]
    fn test_patches_with_no_volumes() {
        let feature = Feature {};
        let values = Values {
            enable_docker_volume: EnableVolumeConfig(false),
            docker_volume_size: VolumeSizeConfig(0),
            docker_volume_type: VolumeTypeConfig("".into()),
            enable_etcd_volume: EnableVolumeConfig(false),
            etcd_volume_size: VolumeSizeConfig(0),
            etcd_volume_type: VolumeTypeConfig("".into()),
            availability_zone: AvailabilityZoneConfig("".into()),
        };

        let patches = feature.patches();
        let mut resources = TestClusterResources::new();
        resources.apply_patches(&patches, &values);
    }

    #[test]
    fn test_patches_with_etcd_volumes_only() {
        let feature = Feature {};
        let values = Values {
            enable_docker_volume: EnableVolumeConfig(false),
            docker_volume_size: VolumeSizeConfig(0),
            docker_volume_type: VolumeTypeConfig("".into()),
            enable_etcd_volume: EnableVolumeConfig(true),
            etcd_volume_size: VolumeSizeConfig(80),
            etcd_volume_type: VolumeTypeConfig("nvme".into()),
            availability_zone: AvailabilityZoneConfig("az1".into()),
        };

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
        let values = Values {
            enable_docker_volume: EnableVolumeConfig(true),
            docker_volume_size: VolumeSizeConfig(160),
            docker_volume_type: VolumeTypeConfig("ssd".into()),
            enable_etcd_volume: EnableVolumeConfig(false),
            etcd_volume_size: VolumeSizeConfig(0),
            etcd_volume_type: VolumeTypeConfig("".into()),
            availability_zone: AvailabilityZoneConfig("az1".into()),
        };

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
        let values = Values {
            enable_docker_volume: EnableVolumeConfig(true),
            docker_volume_size: VolumeSizeConfig(160),
            docker_volume_type: VolumeTypeConfig("ssd".into()),
            enable_etcd_volume: EnableVolumeConfig(true),
            etcd_volume_size: VolumeSizeConfig(80),
            etcd_volume_type: VolumeTypeConfig("nvme".into()),
            availability_zone: AvailabilityZoneConfig("az1".into()),
        };

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
