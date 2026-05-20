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

from types import SimpleNamespace
from unittest import mock

from openstack import exceptions as sdk_exceptions

from magnum.common import exception
from magnum_cluster_api.integrations import openstack


def test_get_resource_value_from_dict():
    assert openstack.get_resource_value({"name": "value"}, "name") == "value"


def test_get_resource_value_uses_default_for_none_dict_value():
    assert openstack.get_resource_value({"hw_disk_bus": None}, "hw_disk_bus", "") == ""


def test_get_resource_value_from_resource_attribute():
    resource = SimpleNamespace(name="value")

    assert openstack.get_resource_value(resource, "name") == "value"


def test_get_resource_value_from_resource_properties():
    resource = SimpleNamespace(properties={"hw_disk_bus": "scsi"})

    assert openstack.get_resource_value(resource, "hw_disk_bus") == "scsi"


def test_get_default_volume_type_uses_cinder_default_endpoint():
    osc = mock.Mock()
    volume_type = SimpleNamespace(name="fast")
    osc.cinder.return_value.get_type.return_value = volume_type

    assert openstack.get_default_volume_type(osc) is volume_type
    osc.cinder.return_value.get_type.assert_called_once_with("default")


def test_get_default_volume_type_falls_back_to_default_type_name():
    osc = mock.Mock()
    volume_type = SimpleNamespace(name="__DEFAULT__")
    cinder = osc.cinder.return_value
    cinder.get_type.side_effect = sdk_exceptions.NotFoundException()
    cinder.find_type.return_value = volume_type

    assert openstack.get_default_volume_type(osc) is volume_type
    cinder.find_type.assert_called_once_with("__DEFAULT__", ignore_missing=True)


def test_list_share_types_uses_shared_file_system_proxy():
    osc = mock.Mock()
    share_types = [SimpleNamespace(name="cephfs")]
    osc.shared_file_system.return_value._list.return_value = share_types

    assert openstack.list_share_types(osc) == share_types
    osc.shared_file_system.return_value._list.assert_called_once_with(
        openstack.ShareType
    )


def test_get_network_value_finds_matching_external_network():
    osc = mock.Mock()
    network = SimpleNamespace(id="net-id", is_router_external=True)
    osc.neutron.return_value.find_network.return_value = network

    assert (
        openstack.get_network_value(
            osc,
            "public",
            "id",
            True,
            exception.ExternalNetworkNotFound,
        )
        == "net-id"
    )
    osc.neutron.return_value.find_network.assert_called_once_with(
        "public", ignore_missing=True
    )


def test_get_network_value_rejects_wrong_external_flag():
    osc = mock.Mock()
    network = SimpleNamespace(id="net-id", is_router_external=True)
    osc.neutron.return_value.find_network.return_value = network

    try:
        openstack.get_network_value(
            osc,
            "private",
            "id",
            False,
            exception.FixedNetworkNotFound,
        )
    except exception.FixedNetworkNotFound:
        pass
    else:
        raise AssertionError("expected FixedNetworkNotFound")


def test_get_subnet_value_finds_subnet():
    osc = mock.Mock()
    subnet = SimpleNamespace(id="subnet-id", name="private-subnet")
    osc.neutron.return_value.find_subnet.return_value = subnet

    assert openstack.get_subnet_value(osc, "private-subnet", "id") == "subnet-id"
    osc.neutron.return_value.find_subnet.assert_called_once_with(
        "private-subnet", ignore_missing=True
    )


def test_get_subnet_value_raises_when_missing():
    osc = mock.Mock()
    osc.neutron.return_value.find_subnet.return_value = None

    try:
        openstack.get_subnet_value(osc, "missing-subnet", "id")
    except exception.FixedSubnetNotFound:
        pass
    else:
        raise AssertionError("expected FixedSubnetNotFound")
