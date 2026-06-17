# Copyright (c) 2023 VEXXHOST, Inc.
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

import textwrap
import types
from unittest import mock

import pykube
import pytest
import responses
from magnum.common import exception
from magnum.tests.unit.objects import utils as magnum_test_utils  # type: ignore
from openstack.load_balancer.v2 import load_balancer as sdk_load_balancer
from oslo_serialization import base64, jsonutils
from oslo_utils import uuidutils
from oslotest import base

from magnum_cluster_api import exceptions, utils


def test_generate_cluster_api_name(mocker):
    mock_cluster_exists = mocker.patch("magnum_cluster_api.utils.cluster_exists")
    mock_cluster_exists.return_value = False

    api = mocker.Mock()

    cluster_api_name = utils.generate_cluster_api_name(api)

    # NOTE(mnaser): We need to make sure that the cluster_api_name is shorter
    #               than X characters so the node names are under 63 characters
    potential_node_name = "-".join(
        [cluster_api_name, "default-worker", "abcde", "abcdefghij"]
    )

    assert len(potential_node_name) <= 63


class TestGenerateCloudControllerManagerConfig:
    @pytest.fixture(autouse=True)
    def setup(self, context, pykube_api, mocker):
        self.context = context
        self.pykube_api = pykube_api

        self.cluster = magnum_test_utils.get_test_cluster(context, labels={})
        self.cluster.cluster_template = magnum_test_utils.get_test_cluster_template(
            self.context
        )

        mock_get_openstack_api = mocker.patch(
            "magnum_cluster_api.clients.get_openstack_api"
        ).return_value
        mock_get_openstack_api.url_for.return_value = "http://localhost/v3"

    def _response_for_cloud_config_secret(self):
        return responses.Response(
            responses.GET,
            "http://localhost/api/%s/namespaces/%s/%s/%s"
            % (
                pykube.Secret.version,
                "magnum-system",
                pykube.Secret.endpoint,
                utils.get_cluster_api_cloud_config_secret_name(self.cluster),
            ),
            json={
                "data": {
                    "clouds.yaml": base64.encode_as_text(
                        jsonutils.dumps(
                            {
                                "clouds": {
                                    "default": {
                                        "region_name": "RegionOne",
                                        "auth": {
                                            "application_credential_id": "fake_application_credential_id",
                                            "application_credential_secret": "fake_application_credential_secret",
                                        },
                                    }
                                }
                            }
                        )
                    ),
                }
            },
        )

    def test_generate_cloud_controller_manager_config(self, mocker, requests_mock):
        with requests_mock as rsps:
            rsps.add(self._response_for_cloud_config_secret())

            config = utils.generate_cloud_controller_manager_config(
                self.context, self.pykube_api, self.cluster
            )

        assert config == textwrap.dedent(
            """\
            [Global]
            auth-url=http://localhost/v3
            region=RegionOne
            application-credential-id=fake_application_credential_id
            application-credential-secret=fake_application_credential_secret
            tls-insecure=false

            [LoadBalancer]
            lb-provider=amphorav2
            lb-method=ROUND_ROBIN
            create-monitor=True
            """
        )

    def test_generate_cloud_controller_manager_config_for_amphora(self, requests_mock):
        self.cluster.labels = {"octavia_provider": "amphora"}

        with requests_mock as rsps:
            rsps.add(self._response_for_cloud_config_secret())

            config = utils.generate_cloud_controller_manager_config(
                self.context, self.pykube_api, self.cluster
            )

        assert config == textwrap.dedent(
            """\
            [Global]
            auth-url=http://localhost/v3
            region=RegionOne
            application-credential-id=fake_application_credential_id
            application-credential-secret=fake_application_credential_secret
            tls-insecure=false

            [LoadBalancer]
            lb-provider=amphora
            lb-method=ROUND_ROBIN
            create-monitor=True
            """
        )

    def test_generate_cloud_controller_manager_config_for_amphora_without_monitor(
        self, requests_mock
    ):
        self.cluster.labels = {
            "octavia_provider": "ovn",
            "octavia_lb_healthcheck": "False",
        }

        with requests_mock as rsps:
            rsps.add(self._response_for_cloud_config_secret())

            config = utils.generate_cloud_controller_manager_config(
                self.context, self.pykube_api, self.cluster
            )

        assert config == textwrap.dedent(
            """\
            [Global]
            auth-url=http://localhost/v3
            region=RegionOne
            application-credential-id=fake_application_credential_id
            application-credential-secret=fake_application_credential_secret
            tls-insecure=false

            [LoadBalancer]
            lb-provider=ovn
            lb-method=SOURCE_IP_PORT
            create-monitor=False
            """
        )

    def test_generate_cloud_controller_manager_config_for_ovn(self, requests_mock):
        self.cluster.labels = {"octavia_provider": "ovn"}

        with requests_mock as rsps:
            rsps.add(self._response_for_cloud_config_secret())

            config = utils.generate_cloud_controller_manager_config(
                self.context, self.pykube_api, self.cluster
            )

        assert config == textwrap.dedent(
            """\
            [Global]
            auth-url=http://localhost/v3
            region=RegionOne
            application-credential-id=fake_application_credential_id
            application-credential-secret=fake_application_credential_secret
            tls-insecure=false

            [LoadBalancer]
            lb-provider=ovn
            lb-method=SOURCE_IP_PORT
            create-monitor=True
            """
        )

    def test_generate_cloud_controller_manager_config_for_ovn_with_correct_algorithm(
        self, requests_mock
    ):
        self.cluster.labels = {
            "octavia_provider": "ovn",
            "octavia_lb_algorithm": "SOURCE_IP_PORT",
        }

        with requests_mock as rsps:
            rsps.add(self._response_for_cloud_config_secret())

            config = utils.generate_cloud_controller_manager_config(
                self.context, self.pykube_api, self.cluster
            )

        assert config == textwrap.dedent(
            """\
            [Global]
            auth-url=http://localhost/v3
            region=RegionOne
            application-credential-id=fake_application_credential_id
            application-credential-secret=fake_application_credential_secret
            tls-insecure=false

            [LoadBalancer]
            lb-provider=ovn
            lb-method=SOURCE_IP_PORT
            create-monitor=True
            """
        )

    def test_generate_cloud_controller_manager_config_for_ovn_with_invalid_algorithm(
        self, requests_mock
    ):
        self.cluster.labels = {
            "octavia_provider": "ovn",
            "octavia_lb_algorithm": "ROUND_ROBIN",
        }

        with requests_mock as rsps:
            rsps.add(self._response_for_cloud_config_secret())

            with pytest.raises(exceptions.InvalidOctaviaLoadBalancerAlgorithm):
                utils.generate_cloud_controller_manager_config(
                    self.context, self.pykube_api, self.cluster
                )


class TestGenerateSystemdProxyConfig:
    def test_with_proxy(self, context):
        cluster = magnum_test_utils.get_test_cluster(context, labels={})
        cluster.cluster_template = magnum_test_utils.get_test_cluster_template(
            context,
            http_proxy="http://proxy.example.com:3128",
            https_proxy="https://proxy.example.com:3128",
            no_proxy="localhost,127.0.0.1",
        )

        config = utils.generate_systemd_proxy_config(cluster)

        assert "[Service]" in config
        assert 'Environment="http_proxy=http://proxy.example.com:3128"' in config
        assert 'Environment="https_proxy=https://proxy.example.com:3128"' in config
        assert 'Environment="no_proxy=localhost,127.0.0.1"' in config

    def test_without_proxy(self, context):
        cluster = magnum_test_utils.get_test_cluster(context, labels={})
        cluster.cluster_template = magnum_test_utils.get_test_cluster_template(
            context, http_proxy=None, https_proxy=None, no_proxy=None
        )

        config = utils.generate_systemd_proxy_config(cluster)

        assert config == ""


class TestGenerateAptProxyConfig:
    def test_with_proxy(self, context):
        cluster = magnum_test_utils.get_test_cluster(context, labels={})
        cluster.cluster_template = magnum_test_utils.get_test_cluster_template(
            context,
            http_proxy="http://proxy.example.com:3128",
            https_proxy="https://proxy.example.com:3128",
        )

        config = utils.generate_apt_proxy_config(cluster)

        assert 'Acquire::http::Proxy "http://proxy.example.com:3128"' in config
        assert 'Acquire::https::Proxy "https://proxy.example.com:3128"' in config

    def test_without_proxy(self, context):
        cluster = magnum_test_utils.get_test_cluster(context, labels={})
        cluster.cluster_template = magnum_test_utils.get_test_cluster_template(
            context, http_proxy=None, https_proxy=None
        )

        config = utils.generate_apt_proxy_config(cluster)

        assert config == ""


@pytest.mark.parametrize("cluster_distro", ["debian", "debian-13"])
def test_get_operating_system_for_debian(context, cluster_distro):
    cluster = magnum_test_utils.get_test_cluster(context, labels={})
    cluster.cluster_template = magnum_test_utils.get_test_cluster_template(
        context,
        cluster_distro=cluster_distro,
    )

    assert utils.get_operating_system(cluster) == "debian"


class TestUtils(base.BaseTestCase):
    """Test case for utils."""

    @mock.patch("magnum.common.neutron.get_network")
    def test_get_fixed_network_id_with_uuid(self, mock_get_network):
        context = mock.Mock()
        fixed_network = uuidutils.generate_uuid()

        network = utils.get_fixed_network_id(context, fixed_network)

        mock_get_network.assert_not_called()
        self.assertEqual(fixed_network, network)

    @mock.patch("magnum.common.neutron.get_network")
    def test_get_fixed_network_id_with_name(self, mock_get_network):
        context = mock.Mock()
        fixed_network = "fake-network"

        network_id = uuidutils.generate_uuid()
        mock_get_network.return_value = network_id

        network = utils.get_fixed_network_id(context, fixed_network)

        mock_get_network.assert_called_once_with(
            context, fixed_network, source="name", target="id", external=False
        )
        self.assertEqual(network_id, network)

    @mock.patch("magnum.common.neutron.get_network")
    def test_get_fixed_network_id_with_no_fixed_network(self, mock_get_network):
        context = mock.Mock()

        network = utils.get_fixed_network_id(context, None)

        mock_get_network.assert_not_called()
        self.assertEqual(None, network)

    @mock.patch("magnum.common.neutron.get_network")
    def test_get_fixed_network_id_with_missing_network(self, mock_get_network):
        context = mock.Mock()
        fixed_network = "fake-network"

        mock_get_network.side_effect = exception.FixedNetworkNotFound(
            network=fixed_network
        )

        self.assertRaises(
            exception.FixedNetworkNotFound,
            utils.get_fixed_network_id,
            context,
            fixed_network,
        )

    @mock.patch("magnum.common.neutron.get_network")
    def test_get_fixed_network_id_with_multiple_networks(self, mock_get_network):
        context = mock.Mock()
        fixed_network = "fake-network"

        mock_get_network.side_effect = exception.Conflict(
            "Multiple networks exist with same name '%s'. Please use the "
            "network ID instead." % fixed_network
        )

        self.assertRaises(
            exception.Conflict,
            utils.get_fixed_network_id,
            context,
            fixed_network,
        )


def test_delete_loadbalancers(mocker):
    ctx = mocker.Mock()
    cluster = mocker.Mock()
    cluster.uuid = "cluster-id"

    load_balancer = {
        "id": "lb-id",
        "description": "Kubernetes service from cluster cluster-id",
        "provisioning_status": "ACTIVE",
        "vip_port_id": "port-id",
    }
    unrelated_load_balancer = {
        "id": "other-lb-id",
        "description": "unrelated",
        "provisioning_status": "ACTIVE",
        "vip_port_id": "other-port-id",
    }
    octavia_admin_client = mocker.Mock()
    octavia_client = mocker.Mock()
    admin_clients = mocker.Mock()
    admin_clients.octavia.return_value = octavia_admin_client
    user_clients = mocker.Mock()
    user_clients.octavia.return_value = octavia_client
    user_clients.list_load_balancers.return_value = [
        load_balancer,
        unrelated_load_balancer,
    ]
    mocker.patch("magnum_cluster_api.utils.context.get_admin_context")
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api",
        side_effect=[admin_clients, user_clients],
    )
    delete_loadbalancers = mocker.patch(
        "magnum_cluster_api.utils.octavia._delete_loadbalancers",
        return_value={"lb-id"},
    )
    wait_for_lb_deleted = mocker.patch(
        "magnum_cluster_api.utils.octavia.wait_for_lb_deleted"
    )

    utils.delete_loadbalancers(ctx, cluster)

    delete_loadbalancers.assert_called_once_with(
        ctx,
        [load_balancer],
        cluster,
        octavia_admin_client,
        remove_fip=True,
    )
    wait_for_lb_deleted.assert_called_once_with(octavia_client, {"lb-id"})


def test_delete_loadbalancers_supports_sdk_load_balancer_proxy(mocker):
    ctx = mocker.Mock()
    cluster = mocker.Mock()
    cluster.uuid = "cluster-id"
    load_balancer = types.SimpleNamespace(
        id="lb-id",
        description="Kubernetes service from cluster cluster-id",
        provisioning_status="ACTIVE",
        vip_port_id="port-id",
    )
    unrelated_load_balancer = types.SimpleNamespace(
        id="other-lb-id",
        description="unrelated",
        provisioning_status="ACTIVE",
        vip_port_id="other-port-id",
    )
    octavia_client = types.SimpleNamespace(
        load_balancers=mocker.Mock(
            side_effect=[[load_balancer, unrelated_load_balancer], []]
        ),
        delete_load_balancer=mocker.Mock(),
    )
    admin_clients = mocker.Mock()
    user_clients = mocker.Mock()
    user_clients.octavia.return_value = octavia_client
    user_clients.list_load_balancers.side_effect = [
        [load_balancer, unrelated_load_balancer]
    ]
    mocker.patch("magnum_cluster_api.utils.context.get_admin_context")
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api",
        side_effect=[admin_clients, user_clients],
    )
    delete_floatingip = mocker.patch(
        "magnum_cluster_api.utils.neutron.delete_floatingip"
    )

    utils.delete_loadbalancers(ctx, cluster)

    octavia_client.delete_load_balancer.assert_called_once_with(
        load_balancer,
        ignore_missing=True,
        cascade=True,
    )
    delete_floatingip.assert_called_once_with(ctx, "port-id", cluster)


def test_delete_loadbalancers_skips_pending_sdk_load_balancers(mocker):
    ctx = mocker.Mock()
    cluster = mocker.Mock()
    cluster.uuid = "cluster-id"
    load_balancer = types.SimpleNamespace(
        id="lb-id",
        description="Kubernetes service from cluster cluster-id",
        provisioning_status="PENDING_DELETE",
        vip_port_id="port-id",
    )
    octavia_client = types.SimpleNamespace(
        load_balancers=mocker.Mock(return_value=[load_balancer]),
        delete_load_balancer=mocker.Mock(),
    )
    admin_clients = mocker.Mock()
    user_clients = mocker.Mock()
    user_clients.octavia.return_value = octavia_client
    user_clients.list_load_balancers.return_value = [load_balancer]
    mocker.patch("magnum_cluster_api.utils.context.get_admin_context")
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api",
        side_effect=[admin_clients, user_clients],
    )
    delete_floatingip = mocker.patch(
        "magnum_cluster_api.utils.neutron.delete_floatingip"
    )

    utils.delete_loadbalancers(ctx, cluster)

    octavia_client.delete_load_balancer.assert_not_called()
    delete_floatingip.assert_not_called()


def test_delete_loadbalancers_supports_generic_sdk_proxy(mocker):
    ctx = mocker.Mock()
    cluster = mocker.Mock()
    cluster.uuid = "cluster-id"
    load_balancer = types.SimpleNamespace(
        id="lb-id",
        description="Kubernetes service from cluster cluster-id",
        provisioning_status="ACTIVE",
        vip_port_id="port-id",
    )
    octavia_client = types.SimpleNamespace(
        _list=mocker.Mock(side_effect=[[load_balancer], []]),
        _delete=mocker.Mock(),
    )
    admin_clients = mocker.Mock()
    user_clients = mocker.Mock()
    user_clients.octavia.return_value = octavia_client
    user_clients.list_load_balancers.return_value = [load_balancer]
    mocker.patch("magnum_cluster_api.utils.context.get_admin_context")
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api",
        side_effect=[admin_clients, user_clients],
    )
    delete_floatingip = mocker.patch(
        "magnum_cluster_api.utils.neutron.delete_floatingip"
    )

    utils.delete_loadbalancers(ctx, cluster)

    octavia_client._delete.assert_called_once_with(
        sdk_load_balancer.LoadBalancer,
        load_balancer,
        ignore_missing=True,
    )
    assert load_balancer.cascade is True
    delete_floatingip.assert_called_once_with(ctx, "port-id", cluster)


def test_wait_for_sdk_loadbalancers_deleted_times_out(mocker):
    lb = types.SimpleNamespace(id="lb-id", provisioning_status="ACTIVE")
    octavia_client = types.SimpleNamespace(
        load_balancers=mocker.Mock(return_value=[lb])
    )
    mocker.patch("magnum_cluster_api.utils.CONF.cluster.pre_delete_lb_timeout", 1)
    mocker.patch("magnum_cluster_api.utils.time.time", side_effect=[0, 0, 2])
    sleep = mocker.patch("magnum_cluster_api.utils.time.sleep")

    with pytest.raises(Exception, match="Timeout waiting for the load balancers"):
        utils._wait_for_sdk_loadbalancers_deleted(octavia_client, {"lb-id"})

    sleep.assert_called_once_with(1)
