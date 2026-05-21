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

from magnum_cluster_api import clients
from magnum_cluster_api.integrations import common


def test_connection_uses_magnum_keystone_session(mocker, context):
    session = mocker.Mock()
    connection = mocker.patch("magnum_cluster_api.clients.sdk_connection.Connection")
    keystone = mocker.patch(
        "magnum_cluster_api.clients.magnum_keystone.KeystoneClientV3"
    )
    keystone.return_value.session = session
    mocker.patch(
        "magnum_cluster_api.clients._get_connection_options",
        return_value={"interface": "internal", "region_name": "RegionOne"},
    )

    conn = clients.get_openstack_connection(context)

    assert conn is connection.return_value
    keystone.assert_called_once_with(context)
    connection.assert_called_once_with(
        session=session,
        interface="internal",
        region_name="RegionOne",
    )


def test_connection_options_normalize_legacy_endpoint_type(mocker):
    mocker.patch(
        "magnum_cluster_api.clients._get_conf_option",
        side_effect=[None, None, None, "RegionOne"],
    )
    mocker.patch(
        "magnum_cluster_api.clients.get_client_option",
        return_value="internalURL",
    )

    assert clients._get_connection_options() == {
        "interface": "internal",
        "region_name": "RegionOne",
    }


def test_connection_options_prefer_keystone_auth_group(mocker):
    mocker.patch(
        "magnum_cluster_api.clients._get_conf_option",
        side_effect=["publicURL", "RegionTwo"],
    )
    get_client_option = mocker.patch("magnum_cluster_api.clients.get_client_option")

    assert clients._get_connection_options() == {
        "interface": "public",
        "region_name": "RegionTwo",
    }
    get_client_option.assert_not_called()


def test_cinder_region_name_uses_identity_proxy(mocker, context):
    conn = mocker.Mock()
    conn.identity.regions.return_value = [SimpleNamespace(id="RegionOne")]
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_connection",
        return_value=conn,
    )

    osc = clients.OpenStackClients(context)
    mocker.patch(
        "magnum_cluster_api.clients.get_client_option", return_value="RegionOne"
    )

    assert osc.cinder_region_name() == "RegionOne"
    conn.identity.regions.assert_called_once_with()


def test_is_service_enabled_uses_identity_proxy(mocker):
    admin_context = mocker.sentinel.admin_context
    service = SimpleNamespace(is_enabled=True)
    conn = mocker.Mock()
    conn.identity.services.return_value = [service]
    mocker.patch(
        "magnum_cluster_api.integrations.common.context.make_admin_context",
        return_value=admin_context,
    )
    get_openstack_connection = mocker.patch(
        "magnum_cluster_api.integrations.common.clients.get_openstack_connection",
        return_value=conn,
    )

    assert common.is_service_enabled("volumev3")
    get_openstack_connection.assert_called_once_with(admin_context)
    conn.identity.services.assert_called_once_with(type="volumev3")
