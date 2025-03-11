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
pub struct FeatureValues {
    #[serde(rename = "hardwareDiskBus")]
    pub hardware_disk_bus: String,

    #[serde(rename = "enableDockerVolume")]
    pub enable_docker_volume: bool,

    #[serde(rename = "dockerVolumeSize")]
    pub docker_volume_size: i64,

    #[serde(rename = "dockerVolumeType")]
    pub docker_volume_type: String,

    #[serde(rename = "enableEtcdVolume")]
    pub enable_etcd_volume: bool,

    #[serde(rename = "etcdVolumeSize")]
    pub etcd_volume_size: i64,

    #[serde(rename = "etcdVolumeType")]
    pub etcd_volume_type: String,

    #[serde(rename = "availabilityZone")]
    pub availability_zone: String,
}

pub struct Feature {}

impl ClusterFeaturePatches for Feature {
    fn patches(&self) -> Vec<ClusterClassPatches> {
        vec![
            ClusterClassPatches {
                name: "addEmptyLists".into(),
                enabled_if: Some(r#"{{ if or .enableEtcdVolume .enableDockerVolume }}true{{ end }}"#.into()),
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
                                path: "/spec/template/spec/additionalBlockDevices".into(),
                                value: Some(Vec::<String>::new().into()),
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
                                path: "/spec/template/spec/kubeadmConfigSpec/mounts".into(),
                                value: Some(Vec::<String>::new().into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems".into(),
                                value: Some(Vec::<String>::new().into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/partitions".into(),
                                value: Some(Vec::<String>::new().into()),
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
                                path: "/spec/template/spec/mounts".into(),
                                value: Some(Vec::<String>::new().into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/diskSetup/filesystems".into(),
                                value: Some(Vec::<String>::new().into()),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/diskSetup/partitions".into(),
                                value: Some(Vec::<String>::new().into()),
                                ..Default::default()
                            }
                        ],
                    },
                ]),
                ..Default::default()
            },
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
                                                {{- if .availabilityZone }}
                                                availabilityZone:
                                                  name: "{{ .availabilityZone }}"
                                                {{- end }}
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
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}b"#.into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}b"#.into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "etcd_disk".into(),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/mounts/-".into(),
                                value: Some(json!(&vec!["LABEL=etcd_disk".to_string(), "/var/lib/etcd".to_string()])),
                                ..Default::default()
                            },
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
                                                    {{- if .availabilityZone }}
                                                    availabilityZone:
                                                      name: "{{ .availabilityZone }}"
                                                    {{- end }}
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
                                value: Some(json!(&vec!["LABEL=docker_disk".to_string(), "/var/lib/containerd".to_string()])),
                                ..Default::default()
                            },
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
                                value: Some(json!(&vec!["LABEL=docker_disk".to_string(), "/var/lib/containerd".to_string()])),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/diskSetup/partitions/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmConfigTemplateTemplateSpecDiskSetupPartitions {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}b"#.into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmConfigTemplateTemplateSpecDiskSetupFilesystems {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}b"#.into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "docker_disk".into(),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
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
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}c"#.into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}c"#.into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "docker_disk".into(),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
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
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}b"#.into(),
                                            layout: true,
                                            overwrite: Some(false),
                                            table_type: Some("gpt".into()),
                                        }).unwrap(),
                                    ),
                                    ..Default::default()
                                }),
                                ..Default::default()
                            },
                            ClusterClassPatchesDefinitionsJsonPatches {
                                op: "add".into(),
                                path: "/spec/template/spec/kubeadmConfigSpec/diskSetup/filesystems/-".into(),
                                value_from: Some(ClusterClassPatchesDefinitionsJsonPatchesValueFrom {
                                    template: Some(
                                        serde_yaml::to_string(&KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                                            device: r#"{{ if eq .hardwareDiskBus "scsi" }}/dev/sd{{ else }}/dev/vd{{end}}b"#.into(),
                                            extra_opts: Some(vec![
                                                "-F".into(),
                                                "-E".into(),
                                                "lazy_itable_init=1,lazy_journal_init=1".into(),
                                            ]),
                                            filesystem: "ext4".into(),
                                            label: "docker_disk".into(),
                                            ..Default::default()
                                        }).unwrap(),
                                    ),
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
        features::test::TestClusterResources,
        resources::fixtures::default_values,
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
        values.enable_etcd_volume = true;
        values.etcd_volume_size = 80;
        values.etcd_volume_type = "nvme".into();

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
                    size_gi_b: values.etcd_volume_size,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.etcd_volume_type),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.availability_zone),
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
            vec![vec![
                "LABEL=etcd_disk".to_string(),
                "/var/lib/etcd".to_string()
            ]]
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
            Vec::<Vec<String>>::new()
        );
    }

    #[test]
    fn test_patches_with_docker_volumes_only() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_docker_volume = true;
        values.docker_volume_size = 160;
        values.docker_volume_type = "ssd".into();

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
                    size_gi_b: values.clone().docker_volume_size,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone),
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
                    size_gi_b: values.clone().docker_volume_size,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone),
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
            vec![vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]]
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
            vec![vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]]
        );
    }

    #[test]
    fn test_patches_with_etcd_and_docker_volumes() {
        let feature = Feature {};

        let mut values = default_values();
        values.enable_etcd_volume = true;
        values.etcd_volume_size = 80;
        values.etcd_volume_type = "nvme".into();
        values.enable_docker_volume = true;
        values.docker_volume_size = 160;
        values.docker_volume_type = "ssd".into();

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
                        size_gi_b: values.clone().etcd_volume_size,
                        storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                            r#type: "Volume".into(),
                            volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                                r#type: Some(values.clone().etcd_volume_type),
                                availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                    name: Some(values.clone().availability_zone),
                                    ..Default::default()
                                })
                            })
                        }
                    },
                    OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                        name: "docker".into(),
                        size_gi_b: values.clone().docker_volume_size,
                        storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                            r#type: "Volume".into(),
                            volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                                r#type: Some(values.clone().docker_volume_type),
                                availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                    name: Some(values.clone().availability_zone),
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
                    size_gi_b: values.docker_volume_size,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone),
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
                vec!["LABEL=etcd_disk".to_string(), "/var/lib/etcd".to_string()],
                vec![
                    "LABEL=docker_disk".to_string(),
                    "/var/lib/containerd".to_string()
                ]
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
            vec![vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]]
        );
    }

    #[test]
    fn test_patches_with_etcd_and_docker_scsi_volumes() {
        let feature = Feature {};

        let mut values = default_values();
        values.hardware_disk_bus = "scsi".to_string();
        values.enable_etcd_volume = true;
        values.etcd_volume_size = 80;
        values.etcd_volume_type = "nvme".into();
        values.enable_docker_volume = true;
        values.docker_volume_size = 160;
        values.docker_volume_type = "ssd".into();

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
                        size_gi_b: values.clone().etcd_volume_size,
                        storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                            r#type: "Volume".into(),
                            volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                                r#type: Some(values.clone().etcd_volume_type),
                                availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                    name: Some(values.clone().availability_zone),
                                    ..Default::default()
                                })
                            })
                        }
                    },
                    OpenStackMachineTemplateTemplateSpecAdditionalBlockDevices {
                        name: "docker".into(),
                        size_gi_b: values.clone().docker_volume_size,
                        storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                            r#type: "Volume".into(),
                            volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                                r#type: Some(values.clone().docker_volume_type),
                                availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                    name: Some(values.clone().availability_zone),
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
                    size_gi_b: values.docker_volume_size,
                    storage: OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorage {
                        r#type: "Volume".into(),
                        volume: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolume {
                            r#type: Some(values.clone().docker_volume_type),
                            availability_zone: Some(OpenStackMachineTemplateTemplateSpecAdditionalBlockDevicesStorageVolumeAvailabilityZone {
                                name: Some(values.clone().availability_zone),
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
                        device: "/dev/sdb".into(),
                        layout: true,
                        overwrite: Some(false),
                        table_type: Some("gpt".into()),
                    },
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupPartitions {
                        device: "/dev/sdc".into(),
                        layout: true,
                        overwrite: Some(false),
                        table_type: Some("gpt".into()),
                    }
                ]),
                filesystems: Some(vec![
                    KubeadmControlPlaneTemplateTemplateSpecKubeadmConfigSpecDiskSetupFilesystems {
                        device: "/dev/sdb".into(),
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
                        device: "/dev/sdc".into(),
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
                vec!["LABEL=etcd_disk".to_string(), "/var/lib/etcd".to_string()],
                vec![
                    "LABEL=docker_disk".to_string(),
                    "/var/lib/containerd".to_string()
                ]
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
                    device: "/dev/sdb".into(),
                    layout: true,
                    overwrite: Some(false),
                    table_type: Some("gpt".into()),
                }]),
                filesystems: Some(vec![
                    KubeadmConfigTemplateTemplateSpecDiskSetupFilesystems {
                        device: "/dev/sdb".into(),
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
            vec![vec![
                "LABEL=docker_disk".to_string(),
                "/var/lib/containerd".to_string()
            ]]
        );
    }
}
