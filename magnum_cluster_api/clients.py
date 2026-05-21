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

import magnum.conf  # type: ignore
import pykube  # type: ignore
from magnum.common import keystone as magnum_keystone  # type: ignore
from openstack import connection as sdk_connection  # type: ignore

CONF = magnum.conf.CONF


SERVICE_CLIENTS = {
    "image": "glance",
    "compute": "nova",
    "network": "neutron",
    "load_balancer": "octavia",
    "block_storage": "cinder",
    "shared_file_system": "manila",
}


def _client_option(client, option):
    client_group = getattr(CONF, f"{client}_client", None)
    if client_group is None:
        return None
    return getattr(client_group, option, None)


def _connection_options():
    options = {}
    shared_endpoint_type = _client_option("openstack", "endpoint_type")
    shared_region_name = _client_option("openstack", "region_name")

    if shared_endpoint_type:
        options["interface"] = shared_endpoint_type
    if shared_region_name:
        options["region_name"] = shared_region_name

    for service_type, client in SERVICE_CLIENTS.items():
        endpoint_type = None
        region_name = None

        if not shared_endpoint_type:
            endpoint_type = _client_option(client, "endpoint_type")
        if not shared_region_name:
            region_name = _client_option(client, "region_name")

        if endpoint_type:
            options[f"{service_type}_interface"] = endpoint_type
        if region_name:
            options[f"{service_type}_region_name"] = region_name
    return options


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> sdk_connection.Connection:
    keystone = magnum_keystone.KeystoneClientV3(context)
    return sdk_connection.Connection(
        session=keystone.session,
        **_connection_options(),
    )


def get_cinder_region_name(context) -> str:
    keystone = magnum_keystone.KeystoneClientV3(context)
    region_name = _client_option("cinder", "region_name")
    return keystone.get_validate_region_name(region_name)
