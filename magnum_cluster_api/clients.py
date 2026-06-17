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

import types

import keystoneauth1  # type: ignore
import openstack.exceptions as sdk_exceptions  # type: ignore
import pykube  # type: ignore
from magnum.common import clients, exception  # type: ignore
from manilaclient.v2 import client as manilaclient  # type: ignore
from novaclient import exceptions as nova_exception  # type: ignore


class OpenStackClients(clients.OpenStackClients):
    """Convenience class to create and cache client instances."""

    def __init__(self, context):
        super(OpenStackClients, self).__init__(context)
        self._manila = None

    @staticmethod
    def _is_callable(obj, attr):
        return callable(getattr(obj, attr, None))

    def create_application_credential(self, user_id, name, description):
        identity = self.keystone().client
        if self._is_callable(identity, "create_application_credential"):
            return identity.create_application_credential(
                user=user_id,
                name=name,
                description=description,
            )

        return identity.application_credentials.create(
            user=user_id,
            name=name,
            description=description,
        )

    def delete_application_credential(self, user_id, name):
        identity = self.keystone().client
        try:
            if self._is_callable(identity, "find_application_credential"):
                credential = identity.find_application_credential(user_id, name)
                if credential is None:
                    return
                identity.delete_application_credential(user_id, credential)
                return

            credential = identity.application_credentials.find(
                name=name,
                user=user_id,
            )
            credential.delete()
        except (
            keystoneauth1.exceptions.http.NotFound,
            keystoneauth1.exceptions.http.Forbidden,
            sdk_exceptions.NotFoundException,
            sdk_exceptions.ForbiddenException,
        ):
            return

    def is_service_enabled(self, service_type):
        identity = self.keystone().client
        if self._is_callable(identity, "services"):
            services = list(identity.services(type=service_type))
        else:
            services = identity.services.list(type=service_type)

        if not services:
            return False

        service = services[0]
        return bool(getattr(service, "is_enabled", getattr(service, "enabled", False)))

    def list_volume_types(self):
        cinder = self.cinder()
        if self._is_callable(cinder, "types"):
            return list(cinder.types())

        return cinder.volume_types.list()

    def get_default_volume_type(self):
        cinder = self.cinder()
        volume_types = getattr(cinder, "volume_types", None)
        if volume_types is not None and self._is_callable(volume_types, "default"):
            return volume_types.default()

        response = cinder.get("/types/default")
        return types.SimpleNamespace(**response.json()["volume_type"])

    def list_flavors(self):
        nova = self.nova()
        if self._is_callable(nova, "flavors"):
            return list(nova.flavors())

        return nova.flavors.list()

    def list_server_groups(self, all_projects=False):
        nova = self.nova()
        if self._is_callable(nova, "server_groups"):
            return list(nova.server_groups(all_projects=all_projects))

        return nova.server_groups.list(all_projects=all_projects)

    def create_server_group(self, name, policies):
        nova = self.nova()
        if self._is_callable(nova, "create_server_group"):
            return nova.create_server_group(name=name, policies=policies)

        return nova.server_groups.create(name=name, policies=policies)

    def delete_server_group(self, server_group_id):
        nova = self.nova()
        try:
            if self._is_callable(nova, "delete_server_group"):
                nova.delete_server_group(server_group_id)
                return

            nova.server_groups.delete(server_group_id)
        except (nova_exception.NotFound, sdk_exceptions.NotFoundException):
            return

    def list_load_balancers(self):
        octavia = self.octavia()
        if self._is_callable(octavia, "load_balancers"):
            return list(octavia.load_balancers())

        return octavia.load_balancer_list().get("loadbalancers", [])

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
