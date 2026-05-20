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
from openstack.shared_file_system.v2 import _proxy as shared_file_system_proxy


class OpenStackClients(clients.OpenStackClients):
    """Convenience class to create and cache client instances."""

    def __init__(self, context):
        super(OpenStackClients, self).__init__(context)
        self._shared_file_system = None

    @exception.wrap_keystone_exception
    def shared_file_system(self):
        if self._shared_file_system:
            return self._shared_file_system
        endpoint_type = self._get_client_option("manila", "endpoint_type")
        region_name = self._get_client_option("manila", "region_name")
        endpoint = self.url_for(
            service_type="sharev2", interface=endpoint_type, region_name=region_name
        )

        session = self.keystone().session
        self._shared_file_system = shared_file_system_proxy.Proxy(
            session,
            service_type="sharev2",
            interface=endpoint_type,
            region_name=region_name,
            endpoint_override=endpoint,
        )
        return self._shared_file_system


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> OpenStackClients:
    return OpenStackClients(context)
