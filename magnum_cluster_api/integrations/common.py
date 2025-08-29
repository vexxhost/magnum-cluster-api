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
from magnum.common import context, exception
from oslo_log import log as logging

from magnum_cluster_api import clients, utils

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
    osc = clients.get_openstack_api(admin_context)
    keystone = osc.keystone()

    try:
        service = keystone.client.services.list(type=service_type)
    except Exception:
        LOG.exception("Failed to list services")
        raise exception.ServicesListFailed()

    if service and service[0].enabled:
        return True

    LOG.info("There is no %s service enabled in the cloud.", service_type)
    return False
