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


class Image:
    def __init__(self, name: str, prefix: str = None):
        self._name = name
        self._prefix = prefix

    @property
    def original_name(self):
        return self._name

    @property
    def name(self):
        if self._prefix is None:
            return self.original_name

        new_image_name = self.original_name
        if hasattr(self, "PREFIX_REPLACEMENTS"):
            for r in self.PREFIX_REPLACEMENTS:
                new_image_name = new_image_name.replace(r, self._prefix)
            return new_image_name

        if self.original_name.startswith("docker.io/calico"):
            return self.original_name.replace(
                "docker.io/calico", f"{self._prefix}/calico"
            )
        if self.original_name.startswith("registry.k8s.io/coredns"):
            return self.original_name.replace("registry.k8s.io/coredns", self._prefix)
        if self.original_name.startswith("registry.k8s.io/autoscaling"):
            return self.original_name.replace(
                "registry.k8s.io/autoscaling", self._prefix
            )
        if (
            self.original_name.startswith("registry.k8s.io/etcd")
            or self.original_name.startswith("registry.k8s.io/kube-")
            or self.original_name.startswith("registry.k8s.io/pause")
        ):
            return self.original_name.replace("registry.k8s.io", self._prefix)

        raise ValueError("Unsupported image: %s" % self.original_name)

    @property
    def repository(self):
        return self.name.split(":")[0]

    @property
    def tag(self):
        return self.name.split(":")[1]


class VersionSpecificImage(Image):
    def __init__(self, version: str, prefix: str = None):
        version = semver.VersionInfo.parse(version[1:])
        config_option = f"v{version.major}_{version.minor}_image"

        if hasattr(self.GROUP, config_option):
            return super().__init__(
                getattr(self.GROUP, config_option),
                prefix,
            )

        raise ValueError(
            f"Unsupported Kubernetes version: {version}. "
            "Please specify a supported version in the cluster template."
        )


class CloudProviderVersionSpecificImage(VersionSpecificImage):
    PREFIX_REPLACEMENTS = ("docker.io/k8scloudprovider", "registry.k8s.io/provider-os")


class CloudControllerManagerImage(CloudProviderVersionSpecificImage):
    GROUP = CONF.cloud_controller_manager


class CinderCSIPluginImage(CloudProviderVersionSpecificImage):
    GROUP = CONF.cinder_csi
