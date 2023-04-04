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

from magnum_cluster_api import image_utils

PAUSE = "registry.k8s.io/pause:3.9"

CLUSTER_AUTOSCALER_V1_22 = "registry.k8s.io/autoscaling/cluster-autoscaler:v1.22.1"
CLUSTER_AUTOSCALER_V1_23 = "registry.k8s.io/autoscaling/cluster-autoscaler:v1.23.0"
CLUSTER_AUTOSCALER_V1_24 = "registry.k8s.io/autoscaling/cluster-autoscaler:v1.24.1"
CLUSTER_AUTOSCALER_V1_25 = "registry.k8s.io/autoscaling/cluster-autoscaler:v1.25.1"
CLUSTER_AUTOSCALER_V1_26 = "registry.k8s.io/autoscaling/cluster-autoscaler:v1.26.1"


def get_cluster_autoscaler_image(version: str, image_repository=None):
    image = None

    version = semver.VersionInfo.parse(version[1:])
    if version.major == 1 and version.minor == 22:
        image = CLUSTER_AUTOSCALER_V1_22
    elif version.major == 1 and version.minor == 23:
        image = CLUSTER_AUTOSCALER_V1_23
    elif version.major == 1 and version.minor == 24:
        image = CLUSTER_AUTOSCALER_V1_24
    elif version.major == 1 and version.minor == 25:
        image = CLUSTER_AUTOSCALER_V1_25
    elif version.major == 1 and version.minor == 26:
        image = CLUSTER_AUTOSCALER_V1_26

    if image:
        return image_utils.get_image(image, image_repository)

    raise ValueError(
        f"Unsupported Kubernetes version: {version}. "
        "Please specify a supported version in the cluster template."
    )
