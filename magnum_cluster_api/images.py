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

import semver

from magnum_cluster_api import conf

CONF = conf.CONF

PAUSE = "registry.k8s.io/pause:3.9"

CLUSTER_AUTOSCALER_LATEST_BY_MINOR = {
    "1.22": "1.22.3",
    "1.23": "1.23.1",
    "1.24": "1.24.3",
    "1.25": "1.25.3",
    "1.26": "1.26.8",
    "1.27": "1.27.8",
    "1.28": "1.28.7",
    "1.29": "1.29.5",
    "1.30": "1.30.7",
    "1.31": "1.31.5",
    "1.32": "1.32.5",
    "1.33": "1.33.3",
    "1.34": "1.34.2",
}


def get_cluster_autoscaler_image(version: str):
    parsed_version = semver.VersionInfo.parse(version[1:])
    cluster_autoscaler_version = CLUSTER_AUTOSCALER_LATEST_BY_MINOR.get(
        f"{parsed_version.major}.{parsed_version.minor}",
        f"{parsed_version.major}.{parsed_version.minor}.0",
    )

    return f"{CONF.auto_scaling.image_repository}/cluster-autoscaler:v{cluster_autoscaler_version}"
