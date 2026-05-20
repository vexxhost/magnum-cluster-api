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
    ("method", "client", "service_type"),
    (
        ("cinder", "cinder", "block-storage"),
        ("neutron", "neutron", "network"),
        ("nova", "nova", "compute"),
        ("octavia", "octavia", "load-balancer"),
        ("shared_file_system", "manila", "sharev2"),
    ),
)
def test_openstack_clients_use_sdk_proxies(method, client, service_type):
    osc = clients.OpenStackClients(mock.Mock())
    sdk_proxy = mock.Mock()
    osc._sdk_proxy = mock.Mock(return_value=sdk_proxy)

    first = getattr(osc, method)()
    second = getattr(osc, method)()

    assert first == sdk_proxy
    assert second == sdk_proxy
    osc._sdk_proxy.assert_called_once()
    assert osc._sdk_proxy.call_args.args[1:] == (client, service_type)


def test_sdk_proxy_uses_service_endpoint(mocker):
    osc = clients.OpenStackClients(mock.Mock())
    osc._get_client_option = mock.Mock(
        side_effect=lambda client, option: {
            ("neutron", "endpoint_type"): "internal",
            ("neutron", "region_name"): "RegionOne",
        }[(client, option)]
    )
    osc.url_for = mock.Mock(return_value="http://neutron.example/v2.0")
    osc.keystone = mock.Mock()
    osc.keystone.return_value.session = mock.Mock()
    proxy = mock.Mock()

    sdk_proxy = osc._sdk_proxy(proxy, "neutron", "network")

    assert sdk_proxy == proxy.Proxy.return_value
    osc.url_for.assert_called_once_with(
        service_type="network",
        interface="internal",
        region_name="RegionOne",
    )
    proxy.Proxy.assert_called_once_with(
        osc.keystone.return_value.session,
        service_type="network",
        interface="internal",
        region_name="RegionOne",
        endpoint_override="http://neutron.example/v2.0",
    )
