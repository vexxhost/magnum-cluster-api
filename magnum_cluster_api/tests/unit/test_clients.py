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


def test_connection_uses_context_access_info(mocker, context):
    access_info = mocker.sentinel.access_info
    auth = mocker.sentinel.auth
    session = mocker.Mock()
    connection = mocker.patch("magnum_cluster_api.clients.sdk_connection.Connection")
    create_access_info = mocker.patch(
        "magnum_cluster_api.clients.ka_access.create",
        return_value=access_info,
    )
    access_plugin = mocker.patch(
        "magnum_cluster_api.clients.ka_access_plugin.AccessInfoPlugin",
        return_value=auth,
    )
    mocker.patch(
        "magnum_cluster_api.clients.get_auth_url",
        return_value="https://keystone.example/v3",
    )
    load_session = mocker.patch(
        "magnum_cluster_api.clients.ka_loading.load_session_from_conf_options",
        return_value=session,
    )

    conn = clients.get_openstack_connection(context)

    assert conn is connection.return_value
    create_access_info.assert_called_once_with(
        body=context.auth_token_info,
        auth_token=context.auth_token,
    )
    access_plugin.assert_called_once_with(
        auth_ref=access_info,
        auth_url="https://keystone.example/v3",
    )
    load_session.assert_called_once_with(
        clients.CONF,
        clients.ksconf.CFG_GROUP,
    )
    assert session.auth is auth
    connection.assert_called_once_with(session=session)


def test_connection_uses_context_token(mocker):
    context = SimpleNamespace(
        auth_token="fake-token",
        auth_token_info=None,
        is_admin=False,
        trust_id=None,
    )
    auth = mocker.sentinel.auth
    session = mocker.Mock()
    token_auth = mocker.patch(
        "magnum_cluster_api.clients.ka_v3.Token",
        return_value=auth,
    )
    mocker.patch(
        "magnum_cluster_api.clients.get_auth_url",
        return_value="https://keystone.example/v3",
    )
    load_session = mocker.patch(
        "magnum_cluster_api.clients.ka_loading.load_session_from_conf_options",
        return_value=session,
    )

    actual_session = clients.get_openstack_session(context)

    assert actual_session is session
    token_auth.assert_called_once_with(
        auth_url="https://keystone.example/v3",
        token="fake-token",
    )
    load_session.assert_called_once_with(
        clients.CONF,
        clients.ksconf.CFG_GROUP,
    )
    assert session.auth is auth


def test_cinder_region_name_uses_identity_proxy(mocker, context):
    conn = mocker.Mock()
    conn.identity.regions.return_value = [SimpleNamespace(id="RegionOne")]
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_connection",
        return_value=conn,
    )

    osc = clients.OpenStackClients(context)
    mocker.patch("magnum_cluster_api.clients.get_client_option", return_value="RegionOne")

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
