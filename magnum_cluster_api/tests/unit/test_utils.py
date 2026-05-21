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
from oslo_serialization import base64, jsonutils
from oslo_utils import uuidutils
from oslotest import base

from magnum_cluster_api import exceptions, utils


class SdkServerGroups:
    def __init__(self, mock):
        self.mock = mock

    def __call__(self, **kwargs):
        return self.mock(**kwargs)


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


def test_get_server_group_id_supports_sdk_compute_proxy(context, mocker):
    mock_cache = mocker.patch("magnum_cluster_api.utils.g_server_group_cache")
    mock_cache.get.return_value = None
    server_group = types.SimpleNamespace(name="kube-test", id="server-group-id")
    server_groups = mocker.Mock(return_value=[server_group])
    nova = types.SimpleNamespace(server_groups=SdkServerGroups(server_groups))
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api"
    ).return_value.nova.return_value = nova

    server_group_id = utils.get_server_group_id(context, "kube-test", "project-id")

    assert server_group_id == "server-group-id"
    server_groups.assert_called_once_with(all_projects=context.is_admin)
    mock_cache.set.assert_called_once_with("project-id", "kube-test", "server-group-id")


def test_ensure_server_group_supports_sdk_compute_proxy(context, mocker):
    mock_cache = mocker.patch("magnum_cluster_api.utils.g_server_group_cache")
    mock_cache.get.return_value = None
    server_group = types.SimpleNamespace(id="server-group-id")
    nova = types.SimpleNamespace(
        server_groups=SdkServerGroups(mocker.Mock(return_value=[])),
        create_server_group=mocker.Mock(return_value=server_group),
    )
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api"
    ).return_value.nova.return_value = nova

    server_group_id = utils._ensure_server_group(
        name="kube-test",
        ctx=context,
        policies=["soft-anti-affinity"],
        project_id="project-id",
    )

    assert server_group_id == "server-group-id"
    nova.create_server_group.assert_called_once_with(
        name="kube-test",
        policies=["soft-anti-affinity"],
    )
    mock_cache.set.assert_called_once_with("project-id", "kube-test", "server-group-id")


def test_delete_server_group_supports_sdk_compute_proxy(context, mocker):
    mocker.patch("magnum_cluster_api.utils.get_server_group_id").return_value = (
        "server-group-id"
    )
    nova = types.SimpleNamespace(
        server_groups=SdkServerGroups(mocker.Mock()),
        delete_server_group=mocker.Mock(),
    )
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api"
    ).return_value.nova.return_value = nova

    utils._delete_server_group("kube-test", context, "project-id")

    nova.delete_server_group.assert_called_once_with(
        "server-group-id",
        ignore_missing=True,
    )


def test_delete_server_group_supports_legacy_nova_client(context, mocker):
    mocker.patch("magnum_cluster_api.utils.get_server_group_id").return_value = (
        "server-group-id"
    )
    nova = types.SimpleNamespace(
        server_groups=types.SimpleNamespace(delete=mocker.Mock()),
    )
    mocker.patch(
        "magnum_cluster_api.clients.get_openstack_api"
    ).return_value.nova.return_value = nova

    utils._delete_server_group("kube-test", context, "project-id")

    nova.server_groups.delete.assert_called_once_with("server-group-id")


def test_volume_type_helpers_support_sdk_block_storage_proxy(mocker):
    volume_type = types.SimpleNamespace(name="rbd1")
    response = mocker.Mock(status_code=200)
    response.json.return_value = {"volume_type": {"id": "type-id", "name": "rbd1"}}
    cinder_client = types.SimpleNamespace(
        types=mocker.Mock(return_value=[volume_type]),
        get=mocker.Mock(return_value=response),
    )

    assert list(utils.list_volume_types(cinder_client)) == [volume_type]
    default_volume_type = utils.get_default_volume_type(cinder_client)

    cinder_client.types.assert_called_once_with()
    cinder_client.get.assert_called_once_with("/types/default")
    assert default_volume_type.id == "type-id"
    assert default_volume_type.name == "rbd1"


def test_default_volume_type_falls_back_for_sdk_block_storage_proxy(mocker):
    volume_type = types.SimpleNamespace(name="fallback")
    response = mocker.Mock(status_code=404)
    cinder_client = types.SimpleNamespace(
        types=mocker.Mock(return_value=iter([volume_type])),
        get=mocker.Mock(return_value=response),
    )

    assert utils.get_default_volume_type(cinder_client) is volume_type
    response.raise_for_status.assert_not_called()


def test_volume_type_helpers_support_legacy_cinder_client(mocker):
    volume_types = [types.SimpleNamespace(name="rbd1")]
    default_volume_type = types.SimpleNamespace(name="rbd1")
    cinder_client = types.SimpleNamespace(
        volume_types=types.SimpleNamespace(
            list=mocker.Mock(return_value=volume_types),
            default=mocker.Mock(return_value=default_volume_type),
        ),
    )

    assert utils.list_volume_types(cinder_client) == volume_types
    assert utils.get_default_volume_type(cinder_client) is default_volume_type


def test_lookup_flavor_supports_sdk_compute_proxy(mocker):
    flavor = types.SimpleNamespace(id="flavor-id", name="m1.large")
    nova = types.SimpleNamespace(
        flavors=SdkServerGroups(mocker.Mock(return_value=[flavor]))
    )
    cli = types.SimpleNamespace(nova=mocker.Mock(return_value=nova))

    assert utils.lookup_flavor(cli, "m1.large") == flavor
    assert utils.lookup_flavor(cli, "flavor-id") == flavor


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
