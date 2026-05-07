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
            lb-provider=amphora
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


def _b64yaml(payload):
    import base64 as _b64

    import yaml as _yaml

    return _b64.b64encode(_yaml.safe_dump(payload).encode()).decode()


class TestExtraCloudInit:
    def _make_cluster(self, labels):
        cluster = mock.Mock()
        cluster.labels = labels
        return cluster

    def _make_node_group(self, labels):
        ng = mock.Mock()
        ng.labels = labels
        return ng

    def test_get_extra_files_empty(self):
        cluster = self._make_cluster({})
        assert utils.get_extra_files(cluster) == []

    def test_get_extra_files_encodes_plain_content(self):
        payload = [{"path": "/etc/netplan/99.yaml", "content": "hello"}]
        cluster = self._make_cluster({"extra_files": _b64yaml(payload)})
        result = utils.get_extra_files(cluster)
        assert result == [
            {
                "path": "/etc/netplan/99.yaml",
                "owner": "root:root",
                "permissions": "0644",
                "content": "aGVsbG8=",
            }
        ]

    def test_get_extra_files_passes_through_base64(self):
        payload = [
            {
                "path": "/etc/foo",
                "content": "aGVsbG8=",
                "encoding": "base64",
                "permissions": "0600",
                "owner": "ubuntu:ubuntu",
            }
        ]
        cluster = self._make_cluster({"extra_files": _b64yaml(payload)})
        result = utils.get_extra_files(cluster)
        assert result[0]["content"] == "aGVsbG8="
        assert result[0]["permissions"] == "0600"
        assert result[0]["owner"] == "ubuntu:ubuntu"

    def test_get_extra_files_node_group_overrides_cluster(self):
        """When the NG declares extra_files, it fully replaces the cluster list."""
        cluster = self._make_cluster(
            {"extra_files": _b64yaml([{"path": "/a", "content": "x"}])}
        )
        ng = self._make_node_group(
            {"extra_files": _b64yaml([{"path": "/b", "content": "y"}])}
        )
        result = utils.get_extra_files(cluster, node_group=ng)
        assert [e["path"] for e in result] == ["/b"]

    def test_get_extra_files_node_group_inherits_when_unset(self):
        """An NG without its own label inherits the cluster-level list."""
        cluster = self._make_cluster(
            {"extra_files": _b64yaml([{"path": "/a", "content": "x"}])}
        )
        ng = self._make_node_group({})
        result = utils.get_extra_files(cluster, node_group=ng)
        assert [e["path"] for e in result] == ["/a"]

    def test_get_extra_files_rejects_relative_path(self):
        cluster = self._make_cluster(
            {"extra_files": _b64yaml([{"path": "etc/foo", "content": "x"}])}
        )
        with pytest.raises(exception.InvalidParameterValue):
            utils.get_extra_files(cluster)

    def test_get_extra_files_rejects_non_list(self):
        import base64 as _b64

        bad = _b64.b64encode(b"not_a_list").decode()
        cluster = self._make_cluster({"extra_files": bad})
        with pytest.raises(exception.InvalidParameterValue):
            utils.get_extra_files(cluster)

    def test_get_extra_files_rejects_invalid_base64(self):
        cluster = self._make_cluster({"extra_files": "!!!not base64!!!"})
        with pytest.raises(exception.InvalidParameterValue):
            utils.get_extra_files(cluster)

    def test_get_extra_files_enforces_cap(self):
        payload = [
            {"path": f"/f{i}", "content": "x"}
            for i in range(utils.EXTRA_CLOUD_INIT_MAX_FILES + 1)
        ]
        cluster = self._make_cluster({"extra_files": _b64yaml(payload)})
        with pytest.raises(exception.InvalidParameterValue):
            utils.get_extra_files(cluster)

    def test_get_extra_pre_kubeadm_commands_split(self):
        cluster = self._make_cluster(
            {"extra_pre_kubeadm_commands": "netplan generate;;netplan apply"}
        )
        assert utils.get_extra_pre_kubeadm_commands(cluster) == [
            "netplan generate",
            "netplan apply",
        ]

    def test_get_extra_pre_kubeadm_commands_node_group_overrides(self):
        """NG label fully replaces cluster-level for that NG."""
        cluster = self._make_cluster({"extra_pre_kubeadm_commands": "a"})
        ng = self._make_node_group({"extra_pre_kubeadm_commands": "b;;c"})
        assert utils.get_extra_pre_kubeadm_commands(cluster, ng) == ["b", "c"]

    def test_get_extra_pre_kubeadm_commands_node_group_inherits(self):
        """NG without its own label inherits the cluster-level commands."""
        cluster = self._make_cluster({"extra_pre_kubeadm_commands": "a;;b"})
        ng = self._make_node_group({})
        assert utils.get_extra_pre_kubeadm_commands(cluster, ng) == ["a", "b"]

    def test_get_extra_pre_kubeadm_commands_drops_empty_segments(self):
        cluster = self._make_cluster({"extra_pre_kubeadm_commands": "a;;;;b;;"})
        assert utils.get_extra_pre_kubeadm_commands(cluster) == ["a", "b"]

    def test_get_extra_post_kubeadm_commands_default_empty(self):
        cluster = self._make_cluster({})
        assert utils.get_extra_post_kubeadm_commands(cluster) == []

    def test_get_extra_pre_kubeadm_commands_enforces_cap(self):
        cmds = ";;".join(
            [f"echo {i}" for i in range(utils.EXTRA_CLOUD_INIT_MAX_PRE_COMMANDS + 1)]
        )
        cluster = self._make_cluster({"extra_pre_kubeadm_commands": cmds})
        with pytest.raises(exception.InvalidParameterValue):
            utils.get_extra_pre_kubeadm_commands(cluster)

    def test_runtime_dispatch_pattern_per_node_via_metadata_service(self):
        """Recommended per-node pattern: one identical dispatch script ships to
        every machine; per-VM behaviour is decided at first boot from the
        OpenStack metadata service (hostname / AZ / server metadata).

        The contract this test locks in:
          * cluster-level ``extra_files`` is delivered identically to control
            plane and to every worker NG that does not declare its own
            ``extra_files`` label;
          * cluster-level ``extra_pre_kubeadm_commands`` likewise inherits;
          * a worker NG that opts out (its own ``extra_files``) cleanly
            replaces the dispatch script with NG-specific content and does
            **not** see the cluster script anymore.
        """
        dispatch_script = (
            "#!/bin/bash\n"
            "META=$(curl -fs http://169.254.169.254/openstack/latest/meta_data.json)\n"
            'ROLE=$(echo "$META" | jq -r \'.meta.node_role // "worker"\')\n'
            '[ "$ROLE" = gpu ] && echo blacklist nouveau >/etc/modprobe.d/nv.conf\n'
        )
        cluster_payload = [
            {
                "path": "/etc/per-node-init.sh",
                "permissions": "0755",
                "content": dispatch_script,
            }
        ]
        cluster = self._make_cluster(
            {
                "extra_files": _b64yaml(cluster_payload),
                "extra_pre_kubeadm_commands": "bash /etc/per-node-init.sh",
            }
        )
        master_ng = self._make_node_group({})
        default_worker = self._make_node_group({})
        opted_out_ng = self._make_node_group(
            {"extra_files": _b64yaml([{"path": "/etc/db.cnf", "content": "x"}])}
        )

        cluster_files = utils.get_extra_files(cluster)
        master_files = utils.get_extra_files(cluster, node_group=master_ng)
        default_worker_files = utils.get_extra_files(cluster, node_group=default_worker)
        opted_out_files = utils.get_extra_files(cluster, node_group=opted_out_ng)

        # Identical dispatch script reaches CP + every inheriting NG.
        assert cluster_files == master_files == default_worker_files
        assert cluster_files[0]["path"] == "/etc/per-node-init.sh"
        assert (
            utils.get_extra_pre_kubeadm_commands(cluster, node_group=master_ng)
            == utils.get_extra_pre_kubeadm_commands(cluster, node_group=default_worker)
            == ["bash /etc/per-node-init.sh"]
        )

        # The opted-out NG fully replaces — no leakage of the dispatch script.
        assert [f["path"] for f in opted_out_files] == ["/etc/db.cnf"]
