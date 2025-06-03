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
    """Test if manifest images match default Calico images."""
    # Calico images to check against
    images = [
        "quay.io/calico/cni",
        "quay.io/calico/kube-controllers",
        "quay.io/calico/node",
    ]

    # Get first default image and extract its version
    default_images = image_loader._get_calico_images()
    first_image = default_images[0]  # e.g., "quay.io/calico/cni:v3.24.2"
    default_version = first_image.split(":")[1]  # e.g., "v3.24.2"

    # Get manifest path
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")
    calico_path = os.path.join(manifests_path, "calico")
    manifest_file = os.path.join(calico_path, f"{default_version}.yaml")

    # Check manifest exists and contains expected images
    assert os.path.exists(
        manifest_file
    ), f"Manifest for version {default_version} not found"
    manifest_images = _get_images_from_manifests(manifest_file)

    # Verify all base images with correct version are in manifest
    expected_images = set(f"{image}:{default_version}" for image in images)
    assert (
        manifest_images == expected_images
    ), f"Manifest images don't match expected Calico images for version {default_version}"


def test__get_infra_images():
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")

    for csi in ["nfs"]:
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
