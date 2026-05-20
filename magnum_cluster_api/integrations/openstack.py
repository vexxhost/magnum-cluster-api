# Copyright (c) 2026 VEXXHOST, Inc.
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

from __future__ import annotations

import typing

from magnum.common import exception  # type: ignore
from openstack import exceptions as sdk_exceptions
from openstack import resource
from openstack.shared_file_system.shared_file_system_service import (
    SharedFilesystemService,
)


class ShareType(resource.Resource):
    resource_key = "share_type"
    resources_key = "share_types"
    base_path = "/types"
    service = SharedFilesystemService("sharev2")

    allow_list = True


def get_resource_value(resource: typing.Any, key: str, default: typing.Any = None):
    if resource is None:
        return default

    if isinstance(resource, dict):
        value = resource.get(key, default)
        return default if value is None else value

    value = getattr(resource, key, None)
    if value is not None:
        return value

    properties = getattr(resource, "properties", None) or {}
    if isinstance(properties, dict):
        value = properties.get(key)
        if value is not None:
            return value

    try:
        value = resource[key]
    except Exception:
        return default
    else:
        return default if value is None else value


def get_image_property(image: typing.Any, key: str, default: typing.Any = None):
    return get_resource_value(image, key, default)


def list_volume_types(osc) -> list[typing.Any]:
    return list(osc.cinder().types())


def get_default_volume_type(osc):
    cinder = osc.cinder()

    try:
        return cinder.get_type("default")
    except sdk_exceptions.SDKException:
        pass

    if callable(getattr(cinder, "find_type", None)):
        return cinder.find_type("__DEFAULT__", ignore_missing=True)

    return None


def list_load_balancers(osc) -> list[typing.Any]:
    return list(osc.octavia().load_balancers())


def delete_load_balancer(osc, load_balancer: typing.Any, cascade: bool = True) -> None:
    osc.octavia().delete_load_balancer(
        load_balancer,
        ignore_missing=True,
        cascade=cascade,
    )


def list_floating_ips(osc, **query) -> list[typing.Any]:
    return list(osc.neutron().ips(**query))


def delete_floating_ip(osc, floating_ip: typing.Any) -> None:
    osc.neutron().delete_ip(floating_ip, ignore_missing=True)


def find_network(osc, name_or_id: str, external: bool):
    network = osc.neutron().find_network(name_or_id, ignore_missing=True)
    if network is None:
        return None

    if get_resource_value(network, "is_router_external", False) != external:
        return None

    return network


def get_network_value(
    osc,
    name_or_id: str,
    target: str,
    external: bool,
    not_found: type[Exception],
):
    network = find_network(osc, name_or_id, external)
    if network is None:
        raise not_found(network=name_or_id)

    return get_resource_value(network, target)


def get_subnet_value(osc, name_or_id: str, target: str):
    subnet = osc.neutron().find_subnet(name_or_id, ignore_missing=True)
    if subnet is None:
        raise exception.FixedSubnetNotFound(subnet=name_or_id)

    return get_resource_value(subnet, target)


def list_flavors(osc) -> list[typing.Any]:
    return list(osc.nova().flavors())


def list_server_groups(osc, all_projects: bool = False) -> list[typing.Any]:
    return list(osc.nova().server_groups(all_projects=all_projects))


def list_share_types(osc) -> list[typing.Any]:
    return list(osc.shared_file_system()._list(ShareType))


def create_server_group(osc, name: str, policies: list[str]):
    return osc.nova().create_server_group(name=name, policies=policies)


def delete_server_group(osc, server_group_id: str) -> None:
    osc.nova().delete_server_group(server_group_id, ignore_missing=True)
