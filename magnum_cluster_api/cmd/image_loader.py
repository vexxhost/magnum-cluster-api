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
import yaml
from diskcache import FanoutCache
from typing import Dict, List, Optional

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
    "v1.27.15",
    "v1.28.11",
    "v1.29.6",
    "v1.30.2",
    "v1.31.1",
]


@click.command()
@click.option(
    "--repository",
    required=True,
    help="Target image repository",
)
@click.option(
    "--config",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=str),
    help="Path to YAML config file containing image configurations",
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
def main(repository, config, parallel, insecure):
    """
    Load images into a remote registry for `container_infra_prefix` usage.
    """

    config_data = load_config(config) if config else None

    # NOTE(mnaser): This list must be maintained manually because the image
    #               registry must be able to support a few different versions
    #               of Kubernetes since it is possible to have multiple
    #               clusters running different versions of Kubernetes at the
    #               same time.
    images = set(
        _get_all_kubeadm_images(config_data)
        + _get_calico_images(config_data)
        + _get_cilium_images(config_data)
        + _get_cloud_provider_images(config_data)
        + _get_infra_images(config_data)
    )

    crane_path = shutil.which("crane")

    if crane_path is None:
        raise click.UsageError(
            """Crane is not installed. Please install it before running this command:
             https://github.com/google/go-containerregistry/blob/main/cmd/crane/README.md#installation"""
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


def _get_all_kubeadm_images(config: Optional[Dict] = None):
    """
    Get the list of images that are used by Kubernetes by downloading "kubeadm"
    and running the "kubeadm config images list" command.
    """

    images = []
    versions = VERSIONS
    if config and "kubernetes" in config:
        versions = config["kubernetes"]["versions"]

    for version in versions:
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


def _get_calico_images(config: Optional[Dict] = None) -> List[str]:
    if config and "calico" in config:
        images = []
        for image in config["calico"]["images"]:
            images.extend(
                [f"{image['name']}:{tag}" for tag in image["tags"]]
            )
        return images

    return [
        f"quay.io/calico/cni:v3.24.2",
        f"quay.io/calico/kube-controllers:v3.24.2",
        f"quay.io/calico/node:v3.24.2",
    ]


def _get_cilium_images(config: Optional[Dict] = None) -> List[str]:
    if config and "cilium" in config:
        images = []
        for image in config["cilium"]["images"]:
            images.extend(
                [f"{image['name']}:{tag}" for tag in image["tags"]]
            )
        return images

    return [
        "quay.io/cilium/cilium:v1.15.3",
        "quay.io/cilium/operator-generic:v1.15.3",
        "quay.io/cilium/cilium:v1.15.6",
        "quay.io/cilium/operator-generic:v1.15.6",
    ]


def _get_cloud_provider_images(config: Optional[Dict] = None) -> List[str]:
    if config and "cloud_provider" in config:
        images = []
        for image in config["cloud_provider"]["images"]:
            images.extend(
                [f"{image['name']}:{tag}" for tag in image["tags"]]
            )
        return images

    return [
        # v1.24.6
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.24.6",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.24.6",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.24.6",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.24.6",
        # v1.25.3
        "docker.io/k8scloudprovider/k8s-keystone-auth:v1.25.3",
        "docker.io/k8scloudprovider/cinder-csi-plugin:v1.25.3",
        "docker.io/k8scloudprovider/manila-csi-plugin:v1.25.3",
        "docker.io/k8scloudprovider/openstack-cloud-controller-manager:v1.25.3",
        # v1.25.6
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.25.6",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.25.6",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.25.6",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.25.6",
        # v1.26.3
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.26.3",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.26.3",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.26.3",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.26.3",
        # v1.27.2
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.27.2",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.27.2",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.27.2",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.27.2",
        # v1.27.3
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.27.3",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.27.3",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.27.3",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.27.3",
        # v1.28.0
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.28.0",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.28.0",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.28.0",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.28.0",
        # v1.28.2
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.28.2",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.28.2",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.28.2",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.28.2",
        # v1.29.0
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.29.0",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.29.0",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.29.0",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.29.0",
        # v1.30.0
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.30.0",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.30.0",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.30.0",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.30.0",
        # v1.31.1
        "registry.k8s.io/provider-os/k8s-keystone-auth:v1.31.1",
        "registry.k8s.io/provider-os/cinder-csi-plugin:v1.31.1",
        "registry.k8s.io/provider-os/manila-csi-plugin:v1.31.1",
        "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.31.1",
    ]


def _get_infra_images(config: Optional[Dict] = None) -> List[str]:
    if config and "infra" in config:
        images = []
        for image in config["infra"]["images"]:
            images.extend(
                [f"{image['name']}:{tag}" for tag in image["tags"]]
            )
        return images

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


def load_config(config_path: str) -> Optional[Dict]:
    """
    Load configuration from YAML file. Missing keys will use default values.
    """

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise click.UsageError("Config file must contain a YAML dictionary")

        if "kubernetes" in config:
            if not isinstance(config["kubernetes"].get("versions", []), list):
                raise click.UsageError("kubernetes.versions must be a list")

        for component in ["calico", "cilium", "cloud_provider", "infra"]:
            if component in config:
                if not isinstance(config[component].get("images", []), list):
                    raise click.UsageError(f"{component}.images must be a list")

                for image in config[component].get("images", []):
                    if not isinstance(image.get("name", ""), str):
                        raise click.UsageError(f"{component} image name must be a string")
                    if not isinstance(image.get("tags", []), list):
                        raise click.UsageError(f"{component} image tags must be a list")

        return config

    except yaml.YAMLError as e:
        raise click.UsageError(f"Failed to parse config file: {e}")
    except OSError as e:
        raise click.UsageError(f"Failed to read config file: {e}")
