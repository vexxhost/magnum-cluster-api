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


def get_cluster_autoscaler_image(version: str):
    version = semver.VersionInfo.parse(version[1:])
    config_option = f"v{version.major}_{version.minor}_image"

    if hasattr(CONF.auto_scaling, config_option):
        return getattr(CONF.auto_scaling, config_option)

    raise ValueError(
        f"Unsupported Kubernetes version: {version}. "
        "Please specify a supported version in the cluster template."
    )
