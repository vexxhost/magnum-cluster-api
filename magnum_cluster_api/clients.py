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
from openstack import connection


class OpenStackClients(clients.OpenStackClients):
    """Convenience class to create and cache client instances."""

    def __init__(self, context):
        super(OpenStackClients, self).__init__(context)
        self._sdk_connection = None
        self._shared_file_system = None

    def _get_sdk_connection(self):
        if self._sdk_connection:
            return self._sdk_connection

        self._sdk_connection = connection.Connection(
            session=self.keystone().session,
            region_name=self._get_client_option("neutron", "region_name"),
            interface=self._get_client_option("neutron", "endpoint_type"),
        )
        return self._sdk_connection

    @exception.wrap_keystone_exception
    def cinder(self):
        if self._cinder:
            return self._cinder

        self._cinder = self._get_sdk_connection().block_storage
        return self._cinder

    @exception.wrap_keystone_exception
    def neutron(self):
        if self._neutron:
            return self._neutron

        self._neutron = self._get_sdk_connection().network
        return self._neutron

    @exception.wrap_keystone_exception
    def nova(self):
        if self._nova:
            return self._nova

        self._nova = self._get_sdk_connection().compute
        return self._nova

    @exception.wrap_keystone_exception
    def octavia(self):
        if self._octavia:
            return self._octavia

        self._octavia = self._get_sdk_connection().load_balancer
        return self._octavia

    @exception.wrap_keystone_exception
    def shared_file_system(self):
        if self._shared_file_system:
            return self._shared_file_system
        self._shared_file_system = self._get_sdk_connection().shared_file_system
        return self._shared_file_system


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> OpenStackClients:
    return OpenStackClients(context)
