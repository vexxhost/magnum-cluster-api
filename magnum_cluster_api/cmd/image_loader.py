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

import concurrent.futures
import os
import shutil
import subprocess
import tempfile

import click
import platformdirs
import requests
from diskcache import FanoutCache

from magnum_cluster_api import image_utils

CACHE = FanoutCache(
    directory=platformdirs.user_cache_dir("magnum_cluster_api", "vexxhost"),
)

# NOTE(mnaser): This is a list of all the Kubernetes versions which we've
#               released images for.  This list is used to determine which
#               images of Kubernetes we should publish to the registry.
VERSIONS = [
    "v1.23.13",
    "v1.23.17",
    "v1.24.7",
    "v1.24.15",
    "v1.25.3",
    "v1.25.11",
    "v1.26.2",
    "v1.26.6",
    "v1.26.11",
    "v1.27.3",
    "v1.27.8",
]


@click.command()
@click.option(
    "--repository",
    required=True,
    help="Target image repository",
)
@click.option(
    "--parallel",
    default=8,
    help="Number of parallel uploads",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Allow insecure connections to the registry.",
)
def main(repository, parallel, insecure):
    """
    Load images into a remote registry for `container_infra_prefix` usage.
    """
    crane_path = shutil.which("crane")

    if crane_path is None:
        raise click.UsageError(
            """Crane is not installed. Please install it before running this command:
             https://github.com/google/go-containerregistry/blob/main/cmd/crane/README.md#installation"""
        )

    # NOTE(mnaser): This list must be maintained manually because the image
    #               registry must be able to support a few different versions
    #               of Kubernetes since it is possible to have multiple
    #               clusters running different versions of Kubernetes at the
    #               same time.
    images = set(
        _get_all_kubeadm_images()
        + _get_calico_images()
        + _get_cloud_provider_images()
        + _get_infra_images()
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
        future_to_image = {
            executor.submit(
                _mirror_image, image, repository, insecure, crane_path
            ): image
            for image in images
        }

        for future in concurrent.futures.as_completed(future_to_image):
            image = future_to_image[future]
            try:
                future.result()
            except Exception as e:
                click.echo(
                    f"Image upload failed for {image}: {e}",
                    err=True,
                )


def _mirror_image(image: str, repository: str, insecure: bool, crane_path: str):
    src = image
    dst = image_utils.get_image(image, repository)

    try:
        command = [crane_path]
        if insecure:
            command.append("--insecure")
        command += ["copy", "--platform", "linux/amd64", src, dst]

        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        click.echo(
            "Image upload failed. Please ensure you're logged in via Crane.",
            err=True,
        )
        return


def _get_all_kubeadm_images():
    """
    Get the list of images that are used by Kubernetes by downloading "kubeadm"
    and running the "kubeadm config images list" command.
    """

    images = []
    for version in VERSIONS:
        images += _get_kubeadm_images(version)

    return images


@CACHE.memoize()
def _get_kubeadm_images(version: str):
    """
    Get the list of images that are used by Kubernetes by downloading "kubeadm"
    and running the "kubeadm config images list" command.
    """

    # Download kubeadm
    r = requests.get(f"https://dl.k8s.io/release/{version}/bin/linux/amd64/kubeadm")
    r.raise_for_status()

    # Write it to a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(r.content)
        f.close()

        # Make it executable
        os.chmod(f.name, 0o755)

        # Run the command
        output = subprocess.check_output(
            [f.name, "config", "images", "list", "--kubernetes-version", version]
        )

        # Remove the temporary file
        os.unlink(f.name)

    # Parse the output
    return output.decode().replace("k8s.gcr.io", "registry.k8s.io").splitlines()


def _get_calico_images():
    return [
        # Calico 3.24.2
        "docker.io/calico/cni:v3.24.2",
        "docker.io/calico/kube-controllers:v3.24.2",
        "docker.io/calico/node:v3.24.2",
    ]


def _get_cloud_provider_images():
    return [
        # 1.24.6
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.24.6",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.24.6",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.24.6",
        # v1.25.3
        "docker.io/k8scloudprovider/cinder-csi-plugin:v1.25.3",
        "docker.io/k8scloudprovider/manila-csi-plugin:v1.25.3",
        "docker.io/k8scloudprovider/openstack-cloud-controller-manager:v1.25.3",
        # v1.25.6
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.25.6",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.25.6",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.25.6",
        # v1.26.3
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.26.3",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.26.3",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.26.3",
        # v1.27.2
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.27.2",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.27.2",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.27.2",
        # v1.28.0
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.28.0",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.28.0",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.28.0",
    ]


def _get_infra_images():
    return [
        "registry.k8s.io/sig-storage/csi-attacher:v3.4.0",
        "registry.k8s.io/sig-storage/csi-attacher:v4.2.0",
        "registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.4.0",
        "registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.5.1",
        "registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.6.2",
        "registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.6.3",
        "registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.9.0",
        "registry.k8s.io/sig-storage/csi-provisioner:v3.0.0",
        "registry.k8s.io/sig-storage/csi-provisioner:v3.1.0",
        "registry.k8s.io/sig-storage/csi-provisioner:v3.3.0",
        "registry.k8s.io/sig-storage/csi-provisioner:v3.4.1",
        "registry.k8s.io/sig-storage/csi-resizer:v1.4.0",
        "registry.k8s.io/sig-storage/csi-resizer:v1.8.0",
        "registry.k8s.io/sig-storage/csi-snapshotter:v5.0.1",
        "registry.k8s.io/sig-storage/csi-snapshotter:v6.0.1",
        "registry.k8s.io/sig-storage/csi-snapshotter:v6.2.1",
        "registry.k8s.io/sig-storage/livenessprobe:v2.7.0",
        "registry.k8s.io/sig-storage/livenessprobe:v2.8.0",
        "registry.k8s.io/sig-storage/livenessprobe:v2.9.0",
        "registry.k8s.io/sig-storage/nfsplugin:v4.2.0",
    ]
