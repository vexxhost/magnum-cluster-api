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

from magnum_cluster_api import clients
from magnum_cluster_api.integrations import cinder, manila


def _keystone(mocker):
    keystone = mocker.Mock()
    keystone.session = "session"
    mocker.patch(
        "magnum_cluster_api.clients.magnum_keystone.KeystoneClientV3",
        return_value=keystone,
    )
    connection = mocker.patch("magnum_cluster_api.clients.sdk_connection.Connection")

    for client in clients.SERVICE_CLIENTS.values():
        group = mocker.Mock()
        group.endpoint_type = "public"
        group.region_name = "RegionOne"
        mocker.patch.object(clients.CONF, f"{client}_client", group)

    return keystone, connection


def test_get_openstack_api_returns_openstacksdk_connection(mocker):
    _, connection = _keystone(mocker)

    result = clients.get_openstack_api(context="context")

    assert result == connection.return_value
    connection.assert_called_once_with(
        session="session",
        image_interface="public",
        image_region_name="RegionOne",
        compute_interface="public",
        compute_region_name="RegionOne",
        network_interface="public",
        network_region_name="RegionOne",
        load_balancer_interface="public",
        load_balancer_region_name="RegionOne",
        block_storage_interface="public",
        block_storage_region_name="RegionOne",
        shared_file_system_interface="public",
        shared_file_system_region_name="RegionOne",
    )


def test_get_openstack_api_skips_unset_service_options(mocker):
    _, connection = _keystone(mocker)

    clients.CONF.cinder_client.endpoint_type = None
    clients.CONF.cinder_client.region_name = None

    connection.reset_mock()

    clients.get_openstack_api(context="context")

    assert "block_storage_interface" not in connection.call_args.kwargs
    assert "block_storage_region_name" not in connection.call_args.kwargs


def test_get_openstack_api_skips_missing_service_config(mocker):
    _, connection = _keystone(mocker)

    mocker.patch.object(clients.CONF, "manila_client", None)

    connection.reset_mock()

    clients.get_openstack_api(context="context")

    assert "shared_file_system_interface" not in connection.call_args.kwargs
    assert "shared_file_system_region_name" not in connection.call_args.kwargs


def test_get_cinder_region_name_uses_magnum_config(mocker):
    keystone, _ = _keystone(mocker)
    keystone.get_validate_region_name.return_value = "RegionOne"

    assert clients.get_cinder_region_name(context="context") == "RegionOne"
    keystone.get_validate_region_name.assert_called_once_with("RegionOne")


def test_get_default_volume_type_uses_openstacksdk_block_storage_proxy(mocker):
    osc = mocker.Mock()
    response = mocker.Mock(status_code=200)
    response.json.return_value = {"volume_type": {"id": "type-id", "name": "fast"}}
    osc.block_storage.get.return_value = response

    default_volume_type = cinder.get_default_volume_type(osc)

    assert default_volume_type.id == "type-id"
    assert default_volume_type.name == "fast"
    osc.block_storage.get.assert_called_once_with("/types/default")


def test_get_default_volume_type_falls_back_to_first_listed_type(mocker):
    osc = mocker.Mock()
    response = mocker.Mock(status_code=404)
    osc.block_storage.get.return_value = response
    volume_types = [mocker.Mock()]
    osc.block_storage.types.return_value = iter(volume_types)

    assert cinder.get_default_volume_type(osc) == volume_types[0]

    response.raise_for_status.assert_not_called()


def test_get_share_types_uses_openstacksdk_shared_file_system_proxy(mocker):
    osc = mocker.Mock()
    response = mocker.Mock()
    response.json.return_value = {
        "share_types": [
            {"id": "share-type-id", "name": "cephfs"},
        ],
    }
    osc.shared_file_system.get.return_value = response

    share_types = manila.get_share_types(osc)

    assert share_types[0].id == "share-type-id"
    assert share_types[0].name == "cephfs"
    osc.shared_file_system.get.assert_called_once_with("/types")
    response.raise_for_status.assert_called_once_with()
