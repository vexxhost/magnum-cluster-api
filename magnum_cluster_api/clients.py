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

import pykube  # type: ignore
from magnum.common import clients, exception  # type: ignore
from openstack.block_storage.v3 import _proxy as block_storage_proxy
from openstack.compute.v2 import _proxy as compute_proxy
from openstack.load_balancer.v2 import _proxy as load_balancer_proxy
from openstack.network.v2 import _proxy as network_proxy
from openstack.shared_file_system.v2 import _proxy as shared_file_system_proxy


class OpenStackClients(clients.OpenStackClients):
    """Convenience class to create and cache client instances."""

    def __init__(self, context):
        super(OpenStackClients, self).__init__(context)
        self._shared_file_system = None

    def _sdk_proxy(self, proxy, client, service_type):
        endpoint_type = self._get_client_option(client, "endpoint_type")
        region_name = self._get_client_option(client, "region_name")
        endpoint = self.url_for(
            service_type=service_type,
            interface=endpoint_type,
            region_name=region_name,
        )

        return proxy.Proxy(
            self.keystone().session,
            service_type=service_type,
            interface=endpoint_type,
            region_name=region_name,
            endpoint_override=endpoint,
        )

    @exception.wrap_keystone_exception
    def cinder(self):
        if self._cinder:
            return self._cinder

        self._cinder = self._sdk_proxy(
            block_storage_proxy,
            "cinder",
            "block-storage",
        )
        return self._cinder

    @exception.wrap_keystone_exception
    def neutron(self):
        if self._neutron:
            return self._neutron

        self._neutron = self._sdk_proxy(
            network_proxy,
            "neutron",
            "network",
        )
        return self._neutron

    @exception.wrap_keystone_exception
    def nova(self):
        if self._nova:
            return self._nova

        self._nova = self._sdk_proxy(
            compute_proxy,
            "nova",
            "compute",
        )
        return self._nova

    @exception.wrap_keystone_exception
    def octavia(self):
        if self._octavia:
            return self._octavia

        self._octavia = self._sdk_proxy(
            load_balancer_proxy,
            "octavia",
            "load-balancer",
        )
        return self._octavia

    @exception.wrap_keystone_exception
    def shared_file_system(self):
        if self._shared_file_system:
            return self._shared_file_system
        self._shared_file_system = self._sdk_proxy(
            shared_file_system_proxy,
            "manila",
            "sharev2",
        )
        return self._shared_file_system


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> OpenStackClients:
    return OpenStackClients(context)
