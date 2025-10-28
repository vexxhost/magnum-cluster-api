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

import pytest
from magnum.objects import fields
from magnum.tests.unit.objects import utils
from novaclient.v2 import flavors  # type: ignore

from magnum_cluster_api import resources


def test_generate_machine_deployments_for_cluster_with_deleting_node_group(
    context, mocker
):
    cluster_template = mocker.Mock()
    cluster_template.labels = {"kube_tag": "v1.26.2"}

    cluster = mocker.Mock()
    cluster.cluster_template = cluster_template
    cluster.labels = {}
    cluster.nodegroups = [
        mocker.Mock(
            name="creating-worker",
            status=fields.ClusterStatus.CREATE_IN_PROGRESS,
            labels={},
        ),
        mocker.Mock(
            name="created-worker",
            status=fields.ClusterStatus.CREATE_COMPLETE,
            labels={},
        ),
        mocker.Mock(
            name="deleting-worker",
            status=fields.ClusterStatus.DELETE_IN_PROGRESS,
            labels={},
        ),
        mocker.Mock(
            name="deleted-worker",
            status=fields.ClusterStatus.DELETE_COMPLETE,
            labels={},
        ),
    ]

    cluster_get_by_uuid = mocker.patch("magnum.objects.Cluster.get_by_uuid")
    cluster_get_by_uuid.return_value = cluster

    mock_get_default_boot_volume_type = mocker.patch(
        "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type"
    )
    mock_get_default_boot_volume_type.return_value = "foo"

    mock_lookup_image = mocker.patch("magnum_cluster_api.utils.lookup_image")
    mock_lookup_image.return_value = {"id": "foo"}

    mock_lookup_flavor = mocker.patch("magnum_cluster_api.utils.lookup_flavor")
    mock_lookup_flavor.return_value = flavors.Flavor(
        None,
        {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1},
    )

    mock_ensure_worker_server_group = mocker.patch(
        "magnum_cluster_api.utils.ensure_worker_server_group"
    )
    mock_ensure_worker_server_group.return_value = "foo"

    mds = resources.generate_machine_deployments_for_cluster(
        context,
        cluster,
    )

    assert len(mds) == 2


@pytest.mark.parametrize(
    "auto_scaling_enabled",
    [True, False, None],
    ids=lambda x: f"auto_scaling_enabled={x}",
)
@pytest.mark.parametrize(
    "auto_healing_enabled",
    [True, False, None],
    ids=lambda x: f"auto_healing_enabled={x}",
)
class TestExistingMutateMachineDeployment:
    @pytest.fixture(autouse=True)
    def setup(self, auto_scaling_enabled, auto_healing_enabled, context, mocker):
        self.cluster = utils.get_test_cluster(context, labels={})
        if auto_scaling_enabled is not None:
            self.cluster.labels["auto_scaling_enabled"] = str(auto_scaling_enabled)

        if auto_healing_enabled is not None:
            self.cluster.labels["auto_healing_enabled"] = str(auto_healing_enabled)

        self.node_group = utils.get_test_nodegroup(context, labels={})
        if auto_scaling_enabled is not None:
            self.node_group.min_node_count = 1
            self.node_group.max_node_count = 3

        mock_lookup_image = mocker.patch("magnum_cluster_api.utils.lookup_image")
        mock_lookup_image.return_value = {"id": "foo"}

        mock_lookup_flavor = mocker.patch("magnum_cluster_api.utils.lookup_flavor")
        mock_lookup_flavor.return_value = flavors.Flavor(
            None,
            {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1},
        )

    def _assert_no_mutations(self, md):
        assert md["name"] == self.node_group.name
        assert "class" not in md

    def _assert_common_machine_deployment_values(self, md):
        assert md["name"] == self.node_group.name
        assert md["metadata"]["labels"] == {
            f"node-role.kubernetes.io/{self.node_group.role}": "",
            "node.cluster.x-k8s.io/nodegroup": self.node_group.name,
        }
        assert (
            md["nodeVolumeDetachTimeout"]
            == resources.CLUSTER_CLASS_NODE_VOLUME_DETACH_TIMEOUT
        )

    def test_mutate_machine_deployment(self, context, auto_scaling_enabled):
        md = resources.mutate_machine_deployment(
            context,
            self.cluster,
            self.node_group,
            {
                "name": self.node_group.name,
            },
        )

        self._assert_common_machine_deployment_values(md)
        self._assert_no_mutations(md)

        if auto_scaling_enabled:
            assert md["replicas"] is None
            assert md["metadata"]["annotations"][
                resources.AUTOSCALE_ANNOTATION_MIN
            ] == str(self.node_group.min_node_count)
            assert md["metadata"]["annotations"][
                resources.AUTOSCALE_ANNOTATION_MAX
            ] == str(self.node_group.max_node_count)
        else:
            assert md["replicas"] == self.node_group.node_count
            assert md["metadata"]["annotations"] == {}


class TestClusterProxyConfiguration:
    """
    Test that proxy configuration values are properly handled when base64-encoded.

    This test class addresses the fix for GitHub issue #790:
    https://github.com/vexxhost/magnum-cluster-api/issues/790

    The issue: When no proxy is configured, empty strings from proxy generation
    functions get base64-encoded, creating invalid YAML that breaks CAPI validation.

    The fix: Use "or '#'" fallback to ensure a harmless comment character is
    encoded instead of an empty string when no proxy is configured.
    """

    @pytest.fixture(autouse=True)
    def setup(self, context, mocker):
        """Setup test fixtures for proxy configuration tests."""
        self.context = context
        self.cluster = utils.get_test_cluster(context, labels={})
        self.cluster.cluster_template = utils.get_test_cluster_template(context)
        self.cluster.stack_id = "test-cluster-stack-id"

        # Mock API clients
        self.api = mocker.Mock()
        self.pykube_api = mocker.Mock()

        # Mock OpenStack API
        mock_osc = mocker.patch("magnum_cluster_api.clients.get_openstack_api")
        self.mock_osc_instance = mock_osc.return_value

        # Mock Cinder volume types
        mock_volume_type = mocker.Mock()
        mock_volume_type.name = "default"
        self.mock_osc_instance.cinder().volume_types.default.return_value = (
            mock_volume_type
        )

        # Mock Nova flavor lookup
        mock_lookup_flavor = mocker.patch("magnum_cluster_api.utils.lookup_flavor")
        mock_lookup_flavor.return_value = flavors.Flavor(
            None,
            {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1},
        )

        # Mock Glance image lookup
        mock_lookup_image = mocker.patch("magnum_cluster_api.utils.lookup_image")
        mock_lookup_image.return_value = {"id": "fake-image-id", "hw_disk_bus": "scsi"}

        # Mock Neutron network
        mock_neutron = mocker.patch("magnum.common.neutron")
        mock_neutron.get_external_network_id.return_value = "fake-network-id"
        mock_neutron.get_fixed_subnet_id.return_value = "fake-subnet-id"

        # Mock server groups
        mocker.patch(
            "magnum_cluster_api.utils.ensure_controlplane_server_group",
            return_value="fake-server-group-id",
        )

    def test_cluster_without_proxy_configuration(self, mocker):
        """
        Test that clusters without proxy configuration get comment fallback.

        When no proxy is configured:
        - generate_systemd_proxy_config() returns ""
        - generate_apt_proxy_config() returns ""
        - The fix ensures "#" is encoded instead of ""
        """
        # Setup cluster without proxy
        self.cluster.cluster_template.http_proxy = None
        self.cluster.cluster_template.https_proxy = None
        self.cluster.cluster_template.no_proxy = None

        # Mock the proxy generation functions to return empty strings
        mock_systemd_proxy = mocker.patch(
            "magnum_cluster_api.utils.generate_systemd_proxy_config",
            return_value="",
        )
        mock_apt_proxy = mocker.patch(
            "magnum_cluster_api.utils.generate_apt_proxy_config", return_value=""
        )

        # Create Cluster resource
        cluster_resource = resources.Cluster(
            self.context, self.api, self.pykube_api, self.cluster
        )
        cluster_obj = cluster_resource.get_object()

        # Verify proxy generation functions were called
        mock_systemd_proxy.assert_called_once_with(self.cluster)
        mock_apt_proxy.assert_called_once_with(self.cluster)

        # Extract the proxy config variables from the cluster spec
        variables = cluster_obj["spec"]["topology"]["variables"]
        systemd_proxy_var = next(
            v for v in variables if v["name"] == "systemdProxyConfig"
        )
        apt_proxy_var = next(v for v in variables if v["name"] == "aptProxyConfig")

        # Import base64 for decoding
        from oslo_serialization import base64

        # Decode the base64 values
        systemd_decoded = base64.decode_as_text(systemd_proxy_var["value"])
        apt_decoded = base64.decode_as_text(apt_proxy_var["value"])

        # Assert: When empty string is returned, fallback to "#" is used
        # The decoded value should be "#" (comment character) not ""
        assert systemd_decoded == "#", (
            f"Expected '#' but got '{systemd_decoded}'. "
            "Empty proxy config should fallback to comment character."
        )
        assert apt_decoded == "#", (
            f"Expected '#' but got '{apt_decoded}'. "
            "Empty proxy config should fallback to comment character."
        )

    def test_cluster_with_proxy_configuration(self, mocker):
        """
        Test that clusters with proxy configuration use actual proxy values.

        When proxy is configured:
        - generate_systemd_proxy_config() returns systemd configuration
        - generate_apt_proxy_config() returns apt configuration
        - The actual configuration should be base64-encoded (not the fallback)
        """
        # Setup cluster with proxy
        self.cluster.cluster_template.http_proxy = "http://proxy.example.com:3128"
        self.cluster.cluster_template.https_proxy = "https://proxy.example.com:3128"
        self.cluster.cluster_template.no_proxy = "localhost,127.0.0.1"

        # Expected proxy configurations (matching what utils.py generates)
        expected_systemd_config = (
            "[Service]\n"
            'Environment="http_proxy=http://proxy.example.com:3128"\n'
            'Environment="HTTP_PROXY=http://proxy.example.com:3128"\n'
            'Environment="https_proxy=https://proxy.example.com:3128"\n'
            'Environment="HTTPS_PROXY=https://proxy.example.com:3128"\n'
            'Environment="no_proxy=localhost,127.0.0.1"\n'
            'Environment="NO_PROXY=localhost,127.0.0.1"\n'
        )

        expected_apt_config = (
            'Acquire::http::Proxy "http://proxy.example.com:3128";\n'
            'Acquire::https::Proxy "https://proxy.example.com:3128";\n'
        )

        # Mock the proxy generation functions to return real configurations
        mock_systemd_proxy = mocker.patch(
            "magnum_cluster_api.utils.generate_systemd_proxy_config",
            return_value=expected_systemd_config,
        )
        mock_apt_proxy = mocker.patch(
            "magnum_cluster_api.utils.generate_apt_proxy_config",
            return_value=expected_apt_config,
        )

        # Create Cluster resource
        cluster_resource = resources.Cluster(
            self.context, self.api, self.pykube_api, self.cluster
        )
        cluster_obj = cluster_resource.get_object()

        # Verify proxy generation functions were called
        mock_systemd_proxy.assert_called_once_with(self.cluster)
        mock_apt_proxy.assert_called_once_with(self.cluster)

        # Extract the proxy config variables
        variables = cluster_obj["spec"]["topology"]["variables"]
        systemd_proxy_var = next(
            v for v in variables if v["name"] == "systemdProxyConfig"
        )
        apt_proxy_var = next(v for v in variables if v["name"] == "aptProxyConfig")

        # Import base64 for decoding
        from oslo_serialization import base64

        # Decode the base64 values
        systemd_decoded = base64.decode_as_text(systemd_proxy_var["value"])
        apt_decoded = base64.decode_as_text(apt_proxy_var["value"])

        # Assert: Actual proxy configurations are encoded (not the fallback)
        assert systemd_decoded == expected_systemd_config, (
            "Systemd proxy config should contain actual proxy settings when configured"
        )
        assert apt_decoded == expected_apt_config, (
            "APT proxy config should contain actual proxy settings when configured"
        )

        # Assert: The fallback "#" should NOT be present
        assert systemd_decoded != "#", "Should not use fallback when proxy is configured"
        assert apt_decoded != "#", "Should not use fallback when proxy is configured"

    def test_empty_string_never_encoded(self, mocker):
        """
        Critical test: Ensure empty strings are NEVER base64-encoded.

        This is the core issue from GitHub #790:
        - Empty strings break YAML parsing in CAPI
        - Must always use "#" fallback for empty proxy configs
        """
        # Force empty string return from proxy functions
        mocker.patch(
            "magnum_cluster_api.utils.generate_systemd_proxy_config", return_value=""
        )
        mocker.patch(
            "magnum_cluster_api.utils.generate_apt_proxy_config", return_value=""
        )

        # Create cluster without proxy
        self.cluster.cluster_template.http_proxy = None
        self.cluster.cluster_template.https_proxy = None

        cluster_resource = resources.Cluster(
            self.context, self.api, self.pykube_api, self.cluster
        )
        cluster_obj = cluster_resource.get_object()

        # Extract variables
        variables = cluster_obj["spec"]["topology"]["variables"]
        systemd_proxy_var = next(
            v for v in variables if v["name"] == "systemdProxyConfig"
        )
        apt_proxy_var = next(v for v in variables if v["name"] == "aptProxyConfig")

        from oslo_serialization import base64

        # Decode values
        systemd_decoded = base64.decode_as_text(systemd_proxy_var["value"])
        apt_decoded = base64.decode_as_text(apt_proxy_var["value"])

        # CRITICAL ASSERTION: Must NEVER be empty string
        assert systemd_decoded != "", (
            "CRITICAL: Empty string must not be encoded. "
            "This breaks CAPI YAML parsing. Must use '#' fallback."
        )
        assert apt_decoded != "", (
            "CRITICAL: Empty string must not be encoded. "
            "This breaks CAPI YAML parsing. Must use '#' fallback."
        )

        # Assert correct fallback is used
        assert systemd_decoded == "#"
        assert apt_decoded == "#"
