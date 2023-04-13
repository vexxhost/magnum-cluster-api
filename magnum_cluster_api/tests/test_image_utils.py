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

import glob
import os
import uuid

import pkg_resources
import pytest
import yaml

from magnum_cluster_api import image_utils


@pytest.mark.parametrize(
    "glob_path",
    [
        "calico/*.yaml",
        "ccm/*.yaml",
        "csi/*.yaml",
    ],
)
def test_update_manifest_images(glob_path):
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")
    repository = "quay.io/test"

    cluster_uuid = str(uuid.uuid4())

    for manifest_file in glob.glob(os.path.join(manifests_path, glob_path)):
        data = image_utils.update_manifest_images(
            cluster_uuid,
            manifest_file,
            repository=repository,
        )

        for doc in yaml.safe_load_all(data):
            if doc["kind"] in ("DaemonSet", "Deployment"):
                for init_container in doc["spec"]["template"]["spec"].get(
                    "initContainers", []
                ):
                    assert init_container["image"].startswith(repository)
                for container in doc["spec"]["template"]["spec"]["containers"]:
                    assert container["image"].startswith(repository)
