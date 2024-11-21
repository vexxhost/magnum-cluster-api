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
        if doc["kind"] in ("DaemonSet", "Deployment", "StatefulSet"):
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

    if not repository:
        return name

    if name.startswith("docker.io/calico"):
        return name.replace("docker.io/calico/", f"{repository}/calico/")
    if name.startswith("quay.io/cilium"):
        return name.replace("quay.io/cilium/", f"{repository}/cilium/")
    if name.startswith(f"{repository}/livenessprobe"):
        return name.replace("livenessprobe", "csi-livenessprobe")

    return repository + "/" + name.split("/")[-1]
