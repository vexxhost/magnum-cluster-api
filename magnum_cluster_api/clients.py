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

import pykube
from magnum.common import clients, exception
from manilaclient.v2 import client as manilaclient


class OpenStackClients(clients.OpenStackClients):
    """Convenience class to create and cache client instances."""

    def __init__(self, context):
        super(OpenStackClients, self).__init__(context)
        self._manila = None

    @exception.wrap_keystone_exception
    def manila(self):
        if self._manila:
            return self._manila
        endpoint_type = self._get_client_option("manila", "endpoint_type")
        region_name = self._get_client_option("manila", "region_name")
        manilaclient_version = self._get_client_option("manila", "api_version")
        endpoint = self.url_for(
            service_type="sharev2", interface=endpoint_type, region_name=region_name
        )
        args = {
            "cacert": self._get_client_option("manila", "ca_file"),
            "insecure": self._get_client_option("manila", "insecure"),
        }

        session = self.keystone().session
        self._manila = manilaclient.Client(
            manilaclient_version, session=session, service_catalog_url=endpoint, **args
        )
        return self._manila


def get_pykube_api() -> pykube.HTTPClient:
    return pykube.HTTPClient(pykube.KubeConfig.from_env())


def get_openstack_api(context) -> OpenStackClients:
    return OpenStackClients(context)
