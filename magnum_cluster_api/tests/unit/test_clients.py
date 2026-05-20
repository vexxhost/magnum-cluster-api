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

from unittest import mock

import pytest

from magnum_cluster_api import clients


@pytest.mark.parametrize(
    ("method", "proxy"),
    (
        ("cinder", "block_storage"),
        ("neutron", "network"),
        ("nova", "compute"),
        ("octavia", "load_balancer"),
        ("shared_file_system", "shared_file_system"),
    ),
)
def test_openstack_clients_use_sdk_proxies(method, proxy):
    osc = clients.OpenStackClients(mock.Mock())
    sdk_connection = mock.Mock()
    osc._get_sdk_connection = mock.Mock(return_value=sdk_connection)

    first = getattr(osc, method)()
    second = getattr(osc, method)()

    assert first == getattr(sdk_connection, proxy)
    assert second == getattr(sdk_connection, proxy)
    osc._get_sdk_connection.assert_called_once()


def test_get_sdk_connection_uses_keystone_session(mocker):
    mock_connection = mocker.patch("magnum_cluster_api.clients.connection.Connection")
    osc = clients.OpenStackClients(mock.Mock())
    osc._get_client_option = mock.Mock(
        side_effect=lambda client, option: {
            ("keystone", "endpoint_type"): "internal",
            ("keystone", "region_name"): "RegionOne",
        }[(client, option)]
    )
    osc.keystone = mock.Mock()
    osc.keystone.return_value.session = mock.Mock()

    sdk_connection = osc._get_sdk_connection()
    cached_connection = osc._get_sdk_connection()

    assert sdk_connection == mock_connection.return_value
    assert cached_connection == mock_connection.return_value
    mock_connection.assert_called_once_with(
        session=osc.keystone.return_value.session,
        region_name="RegionOne",
        interface="internal",
    )
