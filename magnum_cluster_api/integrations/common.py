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
from magnum import objects
from magnum.common import context, exception
from magnum.common.keystone import KeystoneClientV3
from oslo_log import log as logging

from magnum_cluster_api import utils

LOG = logging.getLogger(__name__)


def is_enabled(
    cluster: objects.Cluster,
    label_flag: str,
    service_name: str,
) -> bool:
    return utils.get_cluster_label_as_bool(
        cluster, label_flag, True
    ) and is_service_enabled(service_name)


def is_service_enabled(service_type: str) -> bool:
    """Check if service is deployed in the cloud."""

    admin_context = context.make_admin_context()
    keystone = KeystoneClientV3(admin_context)

    try:
        service = keystone.client.services.list(type=service_type)
    except Exception:
        LOG.exception("Failed to list services")
        raise exception.ServicesListFailed()

    if service and service[0].enabled:
        return True

    LOG.info("There is no %s service enabled in the cloud.", service_type)
    return False


def get_cloud_provider_image(
    cluster: objects.Cluster, tag_label: str, image_name: str
) -> str:
    tag = get_cloud_provider_tag(cluster, tag_label)
    version = semver.VersionInfo.parse(tag[1:])

    repository = "registry.k8s.io/provider-os"
    if version.major == 1 and version.minor < 24:
        repository = "docker.io/k8scloudprovider"

    return f"{repository}/{image_name}:{tag}"


def get_cloud_provider_tag(cluster: objects.Cluster, label: str) -> str:
    tag_label = utils.get_cluster_label(cluster, label, None)
    if tag_label:
        return tag_label

    kube_tag = utils.get_kube_tag(cluster)
    version = semver.VersionInfo.parse(kube_tag[1:])

    tag = None
    if version.major == 1 and version.minor == 23:
        tag = "v1.23.4"
    elif version.major == 1 and version.minor == 24:
        tag = "v1.24.6"
    elif version.major == 1 and version.minor == 25:
        tag = "v1.25.6"
    elif version.major == 1 and version.minor == 26:
        tag = "v1.26.3"
    elif version.major == 1 and version.minor == 27:
        # TODO(mnaser): There is no 1.27 release yet, so we're using
        #               the latest 1.26 release for now.
        tag = "v1.26.3"

    if tag is None:
        raise ValueError(
            f"Unsupported Kubernetes version: {version}. "
            "Please specify a supported version in the cluster template."
        )

    return tag
