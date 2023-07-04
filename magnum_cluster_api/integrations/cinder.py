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

from magnum import objects
from magnum.common import exception
from oslo_config import cfg

from magnum_cluster_api import clients
from magnum_cluster_api.integrations import common

CONF = cfg.CONF


def is_enabled(cluster: objects.Cluster) -> bool:
    return common.is_enabled(cluster, "cinder_csi_enabled", "volumev3")


def get_image(cluster: objects.Cluster) -> str:
    return common.get_cloud_provider_image(
        cluster, "cinder_csi_plugin_tag", "cinder-csi-plugin"
    )


def get_default_boot_volume_type(context):
    """
    Get the default boot volume type since the existing function
    magnum.common.cinder.get_default_boot_volume_type() returns a random volume
    type when CONF.cinder.default_boot_volume_type is not defined.

    Instead of using a random volume type, this function uses the default
    volume type.
    """

    if CONF.cinder.default_boot_volume_type:
        return CONF.cinder.default_boot_volume_type

    osc = clients.get_openstack_api(context)
    default_volume_type = osc.cinder().volume_types.default()

    if default_volume_type is None:
        raise exception.VolumeTypeNotFound()

    return default_volume_type.name
