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

import types
from unittest import mock

from magnum_cluster_api.integrations import common


def test_is_service_enabled_with_keystoneclient_services(mocker):
    mock_osc = mocker.patch("magnum_cluster_api.clients.get_openstack_api").return_value
    services = mock.Mock()
    services.list.return_value = [types.SimpleNamespace(enabled=True)]
    mock_osc.keystone.return_value.client = types.SimpleNamespace(services=services)

    assert common.is_service_enabled("sharev2") is True
    services.list.assert_called_once_with(type="sharev2")


def test_is_service_enabled_with_sdk_services(mocker):
    mock_osc = mocker.patch("magnum_cluster_api.clients.get_openstack_api").return_value
    calls = {}

    def services(**query):
        calls.update(query)
        return iter([types.SimpleNamespace(enabled=True)])

    mock_osc.keystone.return_value.client = types.SimpleNamespace(services=services)

    assert common.is_service_enabled("sharev2") is True
    assert calls == {"type": "sharev2"}


def test_is_service_enabled_without_matching_service(mocker):
    mock_osc = mocker.patch("magnum_cluster_api.clients.get_openstack_api").return_value
    mock_osc.keystone.return_value.client = types.SimpleNamespace(
        services=lambda **query: iter([])
    )

    assert common.is_service_enabled("sharev2") is False
