# Copyright (c) 2024 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import textwrap
from dataclasses import dataclass, field

import yaml

from magnum_cluster_api import objects


@dataclass
class DiskConfig:
    type: str
    mount_path: str


@dataclass
class Volumes:
    control_plane_disks: list[DiskConfig] = field(default_factory=list)
    worker_disks: list[DiskConfig] = field(default_factory=list)

    def _disk_setup(self, disks: list[DiskConfig]) -> dict:
        return {
            "partitions": [
                {
                    "device": f"/dev/vd{chr(ord('a') + index + 1)}",
                    "tableType": "gpt",
                    "layout": True,
                    "overwrite": False,
                }
                for index in range(len(disks))
            ],
            "filesystems": [
                {
                    "label": f"{disk.type}_disk",
                    "filesystem": "ext4",
                    "device": f"/dev/vd{chr(ord('a') + index + 1)}",
                    "extraOpts": [
                        "-F",
                        "-E",
                        "lazy_itable_init=1,lazy_journal_init=1",
                    ],
                }
                for index, disk in enumerate(disks)
            ],
        }

    def _mounts(self, disks: list[DiskConfig]) -> list[list[str]]:
        return [
            [
                f"LABEL={disk.type}_disk",
                disk.mount_path,
            ]
            for disk in disks
        ]

    def _additional_block_devices(self, disks: list[DiskConfig]) -> str:
        return "\n".join(
            [
                textwrap.dedent(
                    f"""\
                - name: {disk.type}
                  sizeGiB: {{{{ .{disk.type}VolumeSize }}}}
                  storage:
                    type: Volume
                    volume:
                      type: "{{{{ .{disk.type}VolumeType }}}}"
                      availabilityZone: "{{{{ .availabilityZone }}}}"
                """
                )
                for disk in disks
            ]
        )

    @property
    def definitions(self) -> list[dict]:
        definitions = []

        if len(self.control_plane_disks) > 0:
            definitions += [
                {
                    "selector": {
                        "apiVersion": objects.OpenStackMachineTemplate.version,
                        "kind": objects.OpenStackMachineTemplate.kind,
                        "matchResources": {
                            "controlPlane": True,
                        },
                    },
                    "jsonPatches": [
                        {
                            "op": "add",
                            "path": "/spec/template/spec/additionalBlockDevices",
                            "valueFrom": {
                                "template": self._additional_block_devices(
                                    self.control_plane_disks
                                ),
                            },
                        },
                    ],
                },
                {
                    "selector": {
                        "apiVersion": objects.KubeadmControlPlaneTemplate.version,
                        "kind": objects.KubeadmControlPlaneTemplate.kind,
                        "matchResources": {
                            "controlPlane": True,
                        },
                    },
                    "jsonPatches": [
                        {
                            "op": "add",
                            "path": "/spec/template/spec/kubeadmConfigSpec/diskSetup",
                            "valueFrom": {
                                "template": yaml.dump(
                                    self._disk_setup(self.control_plane_disks)
                                ),
                            },
                        },
                        {
                            "op": "add",
                            "path": "/spec/template/spec/kubeadmConfigSpec/mounts",
                            "valueFrom": {
                                "template": yaml.dump(
                                    self._mounts(self.control_plane_disks)
                                ),
                            },
                        },
                    ],
                },
            ]

        if len(self.worker_disks) > 0:
            definitions += [
                {
                    "selector": {
                        "apiVersion": objects.OpenStackMachineTemplate.version,
                        "kind": objects.OpenStackMachineTemplate.kind,
                        "matchResources": {
                            "machineDeploymentClass": {
                                "names": ["default-worker"],
                            },
                        },
                    },
                    "jsonPatches": [
                        {
                            "op": "add",
                            "path": "/spec/template/spec/additionalBlockDevices",
                            "valueFrom": {
                                "template": self._additional_block_devices(
                                    self.worker_disks
                                ),
                            },
                        },
                    ],
                },
                {
                    "selector": {
                        "apiVersion": objects.KubeadmConfigTemplate.version,
                        "kind": objects.KubeadmConfigTemplate.kind,
                        "matchResources": {
                            "machineDeploymentClass": {
                                "names": ["default-worker"],
                            }
                        },
                    },
                    "jsonPatches": [
                        {
                            "op": "add",
                            "path": "/spec/template/spec/diskSetup",
                            "valueFrom": {
                                "template": yaml.dump(
                                    self._disk_setup(self.worker_disks)
                                ),
                            },
                        },
                        {
                            "op": "add",
                            "path": "/spec/template/spec/mounts",
                            "valueFrom": {
                                "template": yaml.dump(self._mounts(self.worker_disks)),
                            },
                        },
                    ],
                },
            ]

        return definitions
