# Copyright (c) 2023 VEXXHOST, Inc.
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

import itertools
import os
from pathlib import Path

import pkg_resources
import yaml

from magnum_cluster_api.cmd import image_loader


def _get_images_from_manifests(file: str):
    with open(file) as fd:
        data = fd.read()

    images = []
    for doc in yaml.safe_load_all(data):
        if doc["kind"] in ("DaemonSet", "Deployment", "StatefulSet"):
            for container in itertools.chain(
                doc["spec"]["template"]["spec"].get("initContainers", []),
                doc["spec"]["template"]["spec"]["containers"],
            ):
                images.append(container["image"])

    return set(images)


def test__get_calico_images():
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")

    calico_path = os.path.join(manifests_path, "calico")
    for file in os.listdir(calico_path):
        calico_version = Path(file).stem
        assert _get_images_from_manifests(os.path.join(calico_path, file)) == set(
            image_loader._get_calico_images(tag=calico_version)
        )


def test__get_cloud_provider_images():
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")
    ccm_path = os.path.join(
        manifests_path, "ccm/openstack-cloud-controller-manager-ds.yaml"
    )

    assert _get_images_from_manifests(ccm_path).issubset(
        image_loader._get_cloud_provider_images()
    )


def test__get_infra_images():
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")

    for csi in ["cinder", "manila", "nfs"]:
        folder = os.path.join(manifests_path, f"{csi}-csi")

        for file in os.listdir(folder):
            path = os.path.join(folder, file)

            for image in _get_images_from_manifests(path):
                if image in ("registry.k8s.io/provider-os/manila-csi-plugin:latest",):
                    continue

                assert (
                    image in image_loader._get_infra_images()
                    or image in image_loader._get_cloud_provider_images()
                )
