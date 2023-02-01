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

import yaml


def update_manifest_images(cluster_uuid: str, file, repository=None, replacements=[]):
    with open(file) as fd:
        data = fd.read()

    docs = []
    for doc in yaml.safe_load_all(data):
        # Fix container image paths
        if doc["kind"] in ("DaemonSet", "Deployment"):
            for container in itertools.chain(
                doc["spec"]["template"]["spec"].get("initContainers", []),
                doc["spec"]["template"]["spec"]["containers"],
            ):
                for src, dst in replacements:
                    container["image"] = container["image"].replace(src, dst)
                if repository:
                    container["image"] = get_image(container["image"], repository)

        # Fix CCM cluster-name
        if (
            doc["kind"] == "DaemonSet"
            and doc["metadata"]["name"] == "openstack-cloud-controller-manager"
        ):
            for env in doc["spec"]["template"]["spec"]["containers"][0]["env"]:
                if env["name"] == "CLUSTER_NAME":
                    env["value"] = cluster_uuid

        docs.append(doc)

    return yaml.safe_dump_all(docs, default_flow_style=False)


def get_image(name: str, repository: str = None):
    """
    Get the image name from the target registry given a full image name.
    """

    if repository is None:
        return repository

    new_image_name = name
    if name.startswith("docker.io/calico"):
        new_image_name = name.replace("docker.io/calico/", f"{repository}/calico-")
    if name.startswith("docker.io/k8scloudprovider"):
        new_image_name = name.replace("docker.io/k8scloudprovider", repository)
    if name.startswith("k8s.gcr.io/sig-storage"):
        new_image_name = name.replace("k8s.gcr.io/sig-storage", repository)
    if new_image_name.startswith(f"{repository}/livenessprobe"):
        return new_image_name.replace("livenessprobe", "csi-livenessprobe")
    if new_image_name.startswith("k8s.gcr.io/coredns"):
        return new_image_name.replace("k8s.gcr.io/coredns", repository)
    if (
        new_image_name.startswith("k8s.gcr.io/etcd")
        or new_image_name.startswith("k8s.gcr.io/kube-")
        or new_image_name.startswith("k8s.gcr.io/pause")
    ):
        return new_image_name.replace("k8s.gcr.io", repository)

    assert new_image_name.startswith(repository) is True
    return new_image_name
