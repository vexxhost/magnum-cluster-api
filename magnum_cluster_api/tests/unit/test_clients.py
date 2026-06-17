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

from magnum_cluster_api import clients


def make_openstack_clients(mocker, **client_factories):
    osc = clients.OpenStackClients.__new__(clients.OpenStackClients)
    for name, client in client_factories.items():
        setattr(osc, name, mocker.Mock(return_value=client))
    return osc


def test_create_application_credential_legacy(mocker):
    credential = types.SimpleNamespace(id="app-cred-id", secret="secret")
    manager = types.SimpleNamespace(create=mocker.Mock(return_value=credential))
    identity = types.SimpleNamespace(application_credentials=manager)
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    result = osc.create_application_credential(
        user_id="user-id",
        name="cluster-id",
        description="Magnum cluster",
    )

    assert result == credential
    manager.create.assert_called_once_with(
        user="user-id",
        name="cluster-id",
        description="Magnum cluster",
    )


def test_create_application_credential_sdk(mocker):
    credential = types.SimpleNamespace(id="app-cred-id", secret="secret")
    identity = types.SimpleNamespace(
        create_application_credential=mocker.Mock(return_value=credential)
    )
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    result = osc.create_application_credential(
        user_id="user-id",
        name="cluster-id",
        description="Magnum cluster",
    )

    assert result == credential
    identity.create_application_credential.assert_called_once_with(
        user="user-id",
        name="cluster-id",
        description="Magnum cluster",
    )


def test_delete_application_credential_legacy(mocker):
    credential = types.SimpleNamespace(delete=mocker.Mock())
    manager = types.SimpleNamespace(find=mocker.Mock(return_value=credential))
    identity = types.SimpleNamespace(application_credentials=manager)
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    osc.delete_application_credential(user_id="user-id", name="cluster-id")

    manager.find.assert_called_once_with(name="cluster-id", user="user-id")
    credential.delete.assert_called_once_with()


def test_delete_application_credential_sdk(mocker):
    credential = types.SimpleNamespace(id="app-cred-id")
    identity = types.SimpleNamespace(
        find_application_credential=mocker.Mock(return_value=credential),
        delete_application_credential=mocker.Mock(),
    )
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    osc.delete_application_credential(user_id="user-id", name="cluster-id")

    identity.find_application_credential.assert_called_once_with(
        "user-id", "cluster-id"
    )
    identity.delete_application_credential.assert_called_once_with(
        "user-id", credential
    )


def test_delete_application_credential_sdk_missing(mocker):
    identity = types.SimpleNamespace(
        find_application_credential=mocker.Mock(return_value=None),
        delete_application_credential=mocker.Mock(),
    )
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    osc.delete_application_credential(user_id="user-id", name="cluster-id")

    identity.find_application_credential.assert_called_once_with(
        "user-id", "cluster-id"
    )
    identity.delete_application_credential.assert_not_called()


def test_is_service_enabled_legacy(mocker):
    manager = types.SimpleNamespace(
        list=mocker.Mock(return_value=[types.SimpleNamespace(enabled=True)])
    )
    identity = types.SimpleNamespace(services=manager)
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    assert osc.is_service_enabled("block-storage")
    manager.list.assert_called_once_with(type="block-storage")


def test_is_service_enabled_sdk(mocker):
    identity = types.SimpleNamespace(
        services=mocker.Mock(return_value=[types.SimpleNamespace(is_enabled=True)])
    )
    osc = make_openstack_clients(
        mocker, keystone=types.SimpleNamespace(client=identity)
    )

    assert osc.is_service_enabled("block-storage")
    identity.services.assert_called_once_with(type="block-storage")


def test_list_volume_types_and_default_legacy(mocker):
    volume_type = types.SimpleNamespace(name="fast")
    default_volume_type = types.SimpleNamespace(name="__DEFAULT__")
    manager = types.SimpleNamespace(
        list=mocker.Mock(return_value=[volume_type]),
        default=mocker.Mock(return_value=default_volume_type),
    )
    cinder = types.SimpleNamespace(volume_types=manager)
    osc = make_openstack_clients(mocker, cinder=cinder)

    assert osc.list_volume_types() == [volume_type]
    assert osc.get_default_volume_type() == default_volume_type
    manager.list.assert_called_once_with()
    manager.default.assert_called_once_with()


def test_list_volume_types_and_default_sdk(mocker):
    volume_type = types.SimpleNamespace(name="fast")
    response = types.SimpleNamespace(
        json=mocker.Mock(return_value={"volume_type": {"name": "__DEFAULT__"}})
    )
    cinder = types.SimpleNamespace(
        types=mocker.Mock(return_value=[volume_type]),
        get=mocker.Mock(return_value=response),
    )
    osc = make_openstack_clients(mocker, cinder=cinder)

    assert osc.list_volume_types() == [volume_type]
    assert osc.get_default_volume_type().name == "__DEFAULT__"
    cinder.types.assert_called_once_with()
    cinder.get.assert_called_once_with("/types/default")


def test_flavors_legacy_and_sdk(mocker):
    legacy_flavor = types.SimpleNamespace(id="legacy", name="legacy")
    sdk_flavor = types.SimpleNamespace(id="sdk", name="sdk")

    legacy_osc = make_openstack_clients(
        mocker,
        nova=types.SimpleNamespace(
            flavors=types.SimpleNamespace(
                list=mocker.Mock(return_value=[legacy_flavor])
            )
        ),
    )
    sdk_osc = make_openstack_clients(
        mocker,
        nova=types.SimpleNamespace(flavors=mocker.Mock(return_value=[sdk_flavor])),
    )

    assert legacy_osc.list_flavors() == [legacy_flavor]
    assert sdk_osc.list_flavors() == [sdk_flavor]


def test_server_groups_legacy(mocker):
    server_group = types.SimpleNamespace(id="server-group")
    manager = types.SimpleNamespace(
        list=mocker.Mock(return_value=[server_group]),
        create=mocker.Mock(return_value=server_group),
        delete=mocker.Mock(),
    )
    osc = make_openstack_clients(
        mocker, nova=types.SimpleNamespace(server_groups=manager)
    )

    assert osc.list_server_groups(all_projects=True) == [server_group]
    assert osc.create_server_group("name", ["soft-anti-affinity"]) == server_group
    osc.delete_server_group("server-group")

    manager.list.assert_called_once_with(all_projects=True)
    manager.create.assert_called_once_with(name="name", policies=["soft-anti-affinity"])
    manager.delete.assert_called_once_with("server-group")


def test_server_groups_sdk(mocker):
    server_group = types.SimpleNamespace(id="server-group")
    nova = types.SimpleNamespace(
        server_groups=mocker.Mock(return_value=[server_group]),
        create_server_group=mocker.Mock(return_value=server_group),
        delete_server_group=mocker.Mock(),
    )
    osc = make_openstack_clients(mocker, nova=nova)

    assert osc.list_server_groups(all_projects=True) == [server_group]
    assert osc.create_server_group("name", ["soft-anti-affinity"]) == server_group
    osc.delete_server_group("server-group")

    nova.server_groups.assert_called_once_with(all_projects=True)
    nova.create_server_group.assert_called_once_with(
        name="name", policies=["soft-anti-affinity"]
    )
    nova.delete_server_group.assert_called_once_with("server-group")


def test_load_balancers_legacy(mocker):
    octavia = types.SimpleNamespace(
        load_balancer_list=mocker.Mock(
            return_value={
                "loadbalancers": [
                    {
                        "id": "lb-id",
                        "description": "Kubernetes service from cluster cluster-id",
                        "provisioning_status": "ACTIVE",
                        "vip_port_id": "port-id",
                    }
                ]
            }
        ),
    )
    osc = make_openstack_clients(mocker, octavia=octavia)

    load_balancers = osc.list_load_balancers()

    assert load_balancers[0]["id"] == "lb-id"
    assert load_balancers[0]["vip_port_id"] == "port-id"
    octavia.load_balancer_list.assert_called_once_with()


def test_load_balancers_sdk(mocker):
    load_balancer = types.SimpleNamespace(
        id="lb-id",
        description="Kubernetes service from cluster cluster-id",
        provisioning_status="ACTIVE",
        vip_port_id="port-id",
    )
    octavia = types.SimpleNamespace(
        load_balancers=mocker.Mock(return_value=[load_balancer]),
    )
    osc = make_openstack_clients(mocker, octavia=octavia)

    assert osc.list_load_balancers() == [load_balancer]

    octavia.load_balancers.assert_called_once_with()
