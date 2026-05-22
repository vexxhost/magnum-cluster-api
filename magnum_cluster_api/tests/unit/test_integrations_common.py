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

from magnum_cluster_api.integrations import common


def _openstack_api(mocker, service):
    osc = mocker.Mock()
    osc.identity.services.return_value = [service]
    mocker.patch(
        "magnum_cluster_api.integrations.common.clients.get_openstack_api",
        return_value=osc,
    )
    mocker.patch(
        "magnum_cluster_api.integrations.common.context.make_admin_context",
        return_value="context",
    )
    return osc


def test_is_service_enabled_uses_openstacksdk_is_enabled(mocker):
    service = mocker.Mock()
    service.is_enabled = True
    osc = _openstack_api(mocker, service)

    assert common.is_service_enabled("share")
    osc.identity.services.assert_called_once_with(type="share")


def test_is_service_enabled_supports_legacy_enabled_attribute(mocker):
    service = mocker.Mock(spec=["enabled"])
    service.enabled = True
    _openstack_api(mocker, service)

    assert common.is_service_enabled("share")


def test_is_service_enabled_returns_false_when_service_is_disabled(mocker):
    service = mocker.Mock()
    service.is_enabled = False
    _openstack_api(mocker, service)

    assert not common.is_service_enabled("share")
