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


class TestConfigProfileSelectorLabels:
    def _cluster(self, labels, template_labels):
        cluster = mock.Mock()
        cluster.labels = dict(labels)
        cluster.cluster_template = mock.Mock()
        cluster.cluster_template.labels = dict(template_labels)
        return cluster

    def test_rejects_cluster_create_config_profile_override(self):
        cluster = self._cluster(
            {"config_profile": "profile-user"},
            {"config_profile": "profile-template"},
        )

        with pytest.raises(exception.Invalid):
            utils.reject_config_profile_label_overrides(cluster)

    def test_rejects_cluster_create_config_profile_without_template_label(self):
        cluster = self._cluster({"config_profile": "profile-user"}, {})

        with pytest.raises(exception.Invalid):
            utils.reject_config_profile_label_overrides(cluster)

    def test_allows_matching_config_profile_template_label(self):
        cluster = self._cluster(
            {"config_profile": "profile-template"},
            {"config_profile": "profile-template"},
        )

        utils.reject_config_profile_label_overrides(cluster)

    def test_sync_config_profile_labels_from_template(self):
        cluster = self._cluster(
            {
                "config_profile": "profile-current",
                "nodegroup_config_profile_set": "layout-current",
                "kube_tag": "v1.34.3",
            },
            {},
        )
        template = mock.Mock(
            labels={
                "config_profile": "profile-gpu",
            }
        )

        utils.sync_config_profile_labels_from_template(cluster, template)

        assert cluster.labels["config_profile"] == "profile-gpu"
        assert "nodegroup_config_profile_set" not in cluster.labels
        assert cluster.labels["kube_tag"] == "v1.34.3"


class TestConfigProfiles:
    @pytest.fixture(autouse=True)
    def setup_profiles(self, mocker):
        self.api = mock.Mock()
        self.config_map = mock.Mock(
            obj={
                "data": {
                    "profile-gpu": (
                        "kubeletConfig:\n"
                        "  cpuManagerPolicy: static\n"
                        "  cpuManagerPolicyOptions:\n"
                        '    full-pcpus-only: "true"\n'
                        "  cpuManagerReconcilePeriod: 5s\n"
                        "  memoryManagerPolicy: Static\n"
                        "  topologyManagerPolicy: single-numa-node\n"
                        "  topologyManagerScope: pod\n"
                        "  topologyManagerPolicyOptions:\n"
                        '    max-allowable-numa-nodes: "2"\n'
                        "  qosReserved:\n"
                        '    memory: "50%"\n'
                        "  systemReserved:\n"
                        "    memory: 1Gi\n"
                        "  kubeReserved:\n"
                        "    cpu: 200m\n"
                        "  enforceNodeAllocatable:\n"
                        "    - pods\n"
                        "  reservedMemory:\n"
                        "    - numaNode: 0\n"
                        "      limits:\n"
                        "        memory: 1Gi\n"
                        "  reservedSystemCPUs: 0-1\n"
                        "  maxPods: 250\n"
                    ),
                    "profile-layout": (
                        "nodegroups:\n" "  gpu-workers:\n" "    profile: profile-gpu\n"
                    ),
                }
            }
        )
        self.config_maps = mocker.patch("pykube.ConfigMap.objects").return_value
        self.config_maps.get_or_none.return_value = self.config_map

    def _cluster(self, labels):
        cluster = mock.Mock()
        cluster.labels = dict(labels)
        return cluster

    def _nodegroup(self, name):
        nodegroup = mock.Mock()
        nodegroup.name = name
        return nodegroup

    def _empty_kubelet_config(self):
        return {
            "enabled": False,
            "configYaml": "",
        }

    def _gpu_kubelet_config(self):
        return {
            "enabled": True,
            "configYaml": (
                "cpuManagerPolicy: static\n"
                "  cpuManagerPolicyOptions:\n"
                "    full-pcpus-only: 'true'\n"
                "  cpuManagerReconcilePeriod: 5s\n"
                "  enforceNodeAllocatable:\n"
                "  - pods\n"
                "  kubeReserved:\n"
                "    cpu: 200m\n"
                "  maxPods: 250\n"
                "  memoryManagerPolicy: Static\n"
                "  qosReserved:\n"
                "    memory: 50%\n"
                "  reservedMemory:\n"
                "  - limits:\n"
                "      memory: 1Gi\n"
                "    numaNode: 0\n"
                "  reservedSystemCPUs: 0-1\n"
                "  systemReserved:\n"
                "    memory: 1Gi\n"
                "  topologyManagerPolicy: single-numa-node\n"
                "  topologyManagerPolicyOptions:\n"
                "    max-allowable-numa-nodes: '2'\n"
                "  topologyManagerScope: pod"
            ),
        }

    def _empty_config_profile(self):
        return {
            "enabled": False,
            "kubeletConfig": self._empty_kubelet_config(),
            "filesYaml": [],
            "preKubeadmCommands": [],
            "postKubeadmCommands": [],
        }

    def _gpu_config_profile(self):
        return {
            "enabled": True,
            "kubeletConfig": self._gpu_kubelet_config(),
            "filesYaml": [],
            "preKubeadmCommands": [],
            "postKubeadmCommands": [],
        }

    def test_get_kubelet_config_disabled(self):
        assert (
            utils.get_kubelet_config(self._cluster({})) == self._empty_kubelet_config()
        )

    def test_get_config_profile_disabled(self):
        assert (
            utils.get_config_profile(self._cluster({})) == self._empty_config_profile()
        )

    def test_get_kubelet_config_enabled(self):
        assert (
            utils.get_kubelet_config(
                self._cluster(
                    {
                        "config_profile": "profile-gpu",
                    }
                ),
                self.api,
            )
            == self._gpu_kubelet_config()
        )

    def test_get_config_profile_enabled(self):
        assert (
            utils.get_config_profile(
                self._cluster(
                    {
                        "config_profile": "profile-gpu",
                    }
                ),
                self.api,
            )
            == self._gpu_config_profile()
        )

    def test_get_config_profile_supports_files_and_commands(self):
        self.config_map.obj["data"] = {
            "profile-gpu": (
                "kubeletConfig:\n"
                "  maxPods: 250\n"
                "files:\n"
                "  - path: /etc/gpu-init.sh\n"
                '    permissions: "0755"\n'
                "    content: |\n"
                "      #!/bin/bash\n"
                "      echo gpu\n"
                "preKubeadmCommands:\n"
                "  - bash /etc/gpu-init.sh\n"
                "postKubeadmCommands:\n"
                "  - echo done > /etc/gpu-init.done\n"
            ),
        }

        profile = utils.get_config_profile(
            self._cluster({"config_profile": "profile-gpu"}),
            self.api,
        )

        assert profile["enabled"] is True
        assert profile["kubeletConfig"] == {
            "enabled": True,
            "configYaml": "maxPods: 250",
        }
        assert profile["filesYaml"] == [
            (
                "path: /etc/gpu-init.sh\n"
                "permissions: '0755'\n"
                "content: IyEvYmluL2Jhc2gKZWNobyBncHUK\n"
                "encoding: base64"
            )
        ]
        assert profile["preKubeadmCommands"] == ["bash /etc/gpu-init.sh"]
        assert profile["postKubeadmCommands"] == ["echo done > /etc/gpu-init.done"]

    @pytest.mark.parametrize(
        ("profile_yaml", "expected"),
        [
            (
                "files:\n" "  - path: /etc/profile-file\n" "    content: profile\n",
                {
                    "filesYaml": [
                        (
                            "path: /etc/profile-file\n"
                            "permissions: '0644'\n"
                            "content: cHJvZmlsZQ==\n"
                            "encoding: base64"
                        )
                    ],
                },
            ),
            (
                "preKubeadmCommands:\n" "  - echo pre\n",
                {"preKubeadmCommands": ["echo pre"]},
            ),
            (
                "postKubeadmCommands:\n" "  - echo post\n",
                {"postKubeadmCommands": ["echo post"]},
            ),
        ],
    )
    def test_get_config_profile_supports_solo_profile_keys(
        self,
        profile_yaml,
        expected,
    ):
        self.config_map.obj["data"] = {"profile-gpu": profile_yaml}

        profile = utils.get_config_profile(
            self._cluster({"config_profile": "profile-gpu"}),
            self.api,
        )

        assert profile["enabled"] is True
        for key, value in expected.items():
            assert profile[key] == value

    def test_get_config_profile_preserves_base64_file_content(self):
        self.config_map.obj["data"] = {
            "profile-gpu": (
                "files:\n"
                "  - path: /etc/atmosphere/test-marker\n"
                "    content: ZzItc21va2UtcHIxMDE1Cg==\n"
                "    encoding: base64\n"
            ),
        }

        profile = utils.get_config_profile(
            self._cluster({"config_profile": "profile-gpu"}),
            self.api,
        )

        assert profile["filesYaml"] == [
            (
                "path: /etc/atmosphere/test-marker\n"
                "permissions: '0644'\n"
                "content: ZzItc21va2UtcHIxMDE1Cg==\n"
                "encoding: base64"
            )
        ]

    def test_validate_config_profile_labels(self):
        cluster = self._cluster(
            {
                "config_profile": "profile-gpu",
                "nodegroup_config_profile_set": "profile-layout",
            }
        )

        utils.validate_config_profile_labels(cluster, self.api)

    def test_validate_config_profile_labels_rejects_invalid_profile(self):
        cluster = self._cluster({"config_profile": "exclusive"})

        with pytest.raises(exception.Invalid):
            utils.validate_config_profile_labels(cluster, self.api)

    def test_get_kubelet_config_rejects_invalid_profile(self):
        cluster = self._cluster({"config_profile": "missing"})

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(cluster, self.api)

    def test_get_kubelet_config_rejects_profile_without_api(self):
        cluster = self._cluster({"config_profile": "profile-gpu"})

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(cluster)

    def test_get_config_profile_defaults(self):
        assert (
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-gpu"}),
                self.api,
            )
            == self._gpu_kubelet_config()
        )

    def test_get_config_profile_configures_max_pods(self):
        self.config_map.obj["data"] = {
            "profile-large": (
                "kubeletConfig:\n" "  maxPods: 500\n" "  reservedSystemCPUs: 0-1\n"
            )
        }

        assert utils.get_kubelet_config(
            self._cluster({"config_profile": "profile-large"}),
            self.api,
        ) == {
            "enabled": True,
            "configYaml": "maxPods: 500\n  reservedSystemCPUs: 0-1",
        }

    def test_get_config_profile_preserves_string_reserved_system_cpus(self):
        self.config_map.obj["data"] = {
            "profile-large": ("kubeletConfig:\n" '  reservedSystemCPUs: "0"\n')
        }

        assert utils.get_kubelet_config(
            self._cluster({"config_profile": "profile-large"}),
            self.api,
        ) == {
            "enabled": True,
            "configYaml": "reservedSystemCPUs: '0'",
        }

    def test_get_config_profile_rejects_numeric_reserved_system_cpus(self):
        self.config_map.obj["data"] = {
            "profile-bad": "kubeletConfig:\n  reservedSystemCPUs: 0\n"
        }

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-bad"}),
                self.api,
            )

    def test_get_kubelet_config_rejects_missing_profiles_configmap(self):
        self.config_maps.get_or_none.return_value = None

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-gpu"}),
                self.api,
            )

    def test_get_config_profile_rejects_invalid_yaml(self):
        self.config_map.obj["data"] = {"profile-bad": "not: [valid"}

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-bad"}),
                self.api,
            )

    def test_get_config_profile_allows_dynamic_kubelet_fields(self):
        self.config_map.obj["data"] = {
            "profile-dynamic": (
                "kubeletConfig:\n"
                "  shutdownGracePeriod: 30s\n"
                "  featureGates:\n"
                "    TopologyManagerPolicyOptions: true\n"
                "  topologyManagerScope: pod\n"
            )
        }

        assert utils.get_kubelet_config(
            self._cluster({"config_profile": "profile-dynamic"}),
            self.api,
        ) == {
            "enabled": True,
            "configYaml": (
                "featureGates:\n"
                "    TopologyManagerPolicyOptions: true\n"
                "  shutdownGracePeriod: 30s\n"
                "  topologyManagerScope: pod"
            ),
        }

    def test_get_config_profile_rejects_unwrapped_kubelet_fields(self):
        self.config_map.obj["data"] = {
            "profile-bad": "maxPods: 250\nreservedSystemCPUs: 0-1\n"
        }

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-bad"}),
                self.api,
            )

    def test_get_config_profile_rejects_reserved_field(self):
        self.config_map.obj["data"] = {
            "profile-bad": "kubeletConfig:\n  apiVersion: v1\n"
        }

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-bad"}),
                self.api,
            )

    def test_get_config_profile_rejects_mixed_nodegroups_field(self):
        self.config_map.obj["data"] = {
            "profile-bad": (
                "nodegroups:\n"
                "  gpu-workers:\n"
                "    profile: profile-gpu\n"
                "maxPods: 250\n"
            )
        }

        with pytest.raises(exception.Invalid):
            utils.get_kubelet_config(
                self._cluster({"config_profile": "profile-bad"}),
                self.api,
            )

    def test_get_nodegroup_kubelet_config(self):
        cluster = self._cluster({"nodegroup_config_profile_set": "profile-layout"})
        nodegroup = self._nodegroup("gpu-workers")

        assert (
            utils.get_nodegroup_kubelet_config(cluster, nodegroup, self.api)
            == self._gpu_kubelet_config()
        )

    def test_get_nodegroup_config_profile(self):
        self.config_map.obj["data"]["profile-layout"] = (
            "nodegroups:\n" "  gpu-workers:\n" "    profile: profile-gpu\n"
        )
        cluster = self._cluster({"nodegroup_config_profile_set": "profile-layout"})
        nodegroup = self._nodegroup("gpu-workers")

        assert (
            utils.get_nodegroup_config_profile(cluster, nodegroup, self.api)
            == self._gpu_config_profile()
        )

    def test_get_nodegroup_config_profile_supports_distinct_files(self):
        self.config_map.obj["data"] = {
            "profile-standard": (
                "files:\n"
                "  - path: /etc/atmosphere/role\n"
                "    content: standard\n"
                "preKubeadmCommands:\n"
                "  - cat /etc/atmosphere/role\n"
            ),
            "profile-gpu": (
                "files:\n"
                "  - path: /etc/atmosphere/role\n"
                "    content: gpu\n"
                "preKubeadmCommands:\n"
                "  - cat /etc/atmosphere/role\n"
            ),
            "profile-layout": (
                "nodegroups:\n" "  gpu-workers:\n" "    profile: profile-gpu\n"
            ),
        }
        cluster = self._cluster(
            {
                "config_profile": "profile-standard",
                "nodegroup_config_profile_set": "profile-layout",
            }
        )

        default_profile = utils.get_config_profile(cluster, self.api)
        gpu_profile = utils.get_nodegroup_config_profile(
            cluster,
            self._nodegroup("gpu-workers"),
            self.api,
        )

        assert "content: c3RhbmRhcmQ=" in default_profile["filesYaml"][0]
        assert "content: Z3B1" in gpu_profile["filesYaml"][0]
        assert default_profile["preKubeadmCommands"] == ["cat /etc/atmosphere/role"]
        assert gpu_profile["preKubeadmCommands"] == ["cat /etc/atmosphere/role"]

    def test_get_nodegroup_kubelet_config_ignores_unmapped_nodegroup(self):
        cluster = self._cluster({"nodegroup_config_profile_set": "profile-layout"})
        nodegroup = self._nodegroup("default-worker")

        assert utils.get_nodegroup_kubelet_config(cluster, nodegroup, self.api) is None

    def test_get_nodegroup_kubelet_config_rejects_invalid_profile_set(self):
        cluster = self._cluster({"nodegroup_config_profile_set": "missing-layout"})
        nodegroup = self._nodegroup("gpu-workers")

        with pytest.raises(exception.Invalid):
            utils.get_nodegroup_kubelet_config(cluster, nodegroup, self.api)

    def test_get_nodegroup_kubelet_config_rejects_missing_profile_reference(self):
        self.config_map.obj["data"]["profile-layout"] = (
            "nodegroups:\n" "  gpu-workers:\n" "    profile: missing-profile\n"
        )
        cluster = self._cluster({"nodegroup_config_profile_set": "profile-layout"})
        nodegroup = self._nodegroup("gpu-workers")

        with pytest.raises(exception.Invalid):
            utils.get_nodegroup_kubelet_config(cluster, nodegroup, self.api)

    def test_get_nodegroup_kubelet_config_rejects_invalid_layout_schema(self):
        self.config_map.obj["data"]["profile-layout"] = (
            "nodegroups:\n" "  gpu-workers:\n" "    maxPods: 250\n"
        )
        cluster = self._cluster({"nodegroup_config_profile_set": "profile-layout"})
        nodegroup = self._nodegroup("gpu-workers")

        with pytest.raises(exception.Invalid):
            utils.get_nodegroup_kubelet_config(cluster, nodegroup, self.api)

    def test_get_kubelet_config_fetches_profile_configmap(self):
        utils.get_kubelet_config(
            self._cluster({"config_profile": "profile-gpu"}),
            self.api,
        )

        pykube.ConfigMap.objects.assert_called_once_with(
            self.api,
            namespace="magnum-system",
        )
        self.config_maps.get_or_none.assert_called_once_with(
            name="mcapi-config-profiles"
        )
