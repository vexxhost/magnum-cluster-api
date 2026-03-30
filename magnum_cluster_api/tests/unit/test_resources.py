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
from oslo_utils import uuidutils

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
            assert md["metadata"]["annotations"][
                "capacity.cluster-autoscaler.kubernetes.io/labels"
            ] == (
                f"node-role.kubernetes.io/{self.node_group.role}=,"
                f"node.cluster.x-k8s.io/nodegroup={self.node_group.name}"
            )
        else:
            assert md["replicas"] == self.node_group.node_count
            assert md["metadata"]["annotations"] == {}


def _get_api_server_lb_variable(obj):
    """Extract apiServerLoadBalancer from a Cluster get_object() result."""
    variables = obj["spec"]["topology"]["variables"]
    for v in variables:
        if v["name"] == "apiServerLoadBalancer":
            return v["value"]
    raise AssertionError("apiServerLoadBalancer variable not found")


class TestClusterOctaviaProviderSelection:
    """Tests for the octavia provider precedence logic in Cluster.get_object().

    Precedence:
      1. Label ``octavia_provider`` explicitly set → always use it.
      2. Existing CAPI Cluster found (upgrade) → preserve its provider.
      3. New cluster, no label → default to ``amphorav2``.
    """

    @pytest.fixture(autouse=True)
    def setup(self, context, mocker):
        self.context = context
        self.mocker = mocker

        # --- Stub heavy OpenStack / K8s dependencies of get_object() ---
        mock_osc = mocker.patch(
            "magnum_cluster_api.clients.get_openstack_api"
        ).return_value
        mock_osc.cinder.return_value.volume_types.default.return_value.name = (
            "__DEFAULT__"
        )

        fake_flavor = flavors.Flavor(
            None, {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1}
        )
        mocker.patch("magnum_cluster_api.utils.lookup_flavor", return_value=fake_flavor)
        mocker.patch(
            "magnum_cluster_api.utils.lookup_image", return_value={"id": "img-1"}
        )
        mocker.patch(
            "magnum_cluster_api.resources.generate_machine_deployments_for_cluster",
            return_value=[],
        )
        mocker.patch(
            "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type",
            return_value="__DEFAULT__",
        )
        mocker.patch(
            "magnum.common.neutron.get_external_network_id",
            return_value="ext-net-id",
        )
        mocker.patch("magnum_cluster_api.utils.get_fixed_network_id", return_value="")
        mocker.patch("magnum.common.neutron.get_fixed_subnet_id", return_value="")
        mocker.patch(
            "magnum_cluster_api.utils.ensure_controlplane_server_group",
            return_value="sg-1",
        )

    def _make_magnum_cluster(self, labels=None):
        """Build a mock Magnum cluster with sensible defaults."""
        all_labels = {"kube_tag": "v1.26.2"}
        if labels:
            all_labels.update(labels)

        cluster_template = self.mocker.Mock()
        cluster_template.network_driver = "calico"
        cluster_template.dns_nameserver = "8.8.8.8"
        cluster_template.external_network_id = uuidutils.generate_uuid()

        ng_master = self.mocker.Mock()
        ng_master.image_id = uuidutils.generate_uuid()

        cluster = self.mocker.Mock()
        cluster.cluster_template = cluster_template
        cluster.labels = all_labels
        cluster.master_flavor_id = uuidutils.generate_uuid()
        cluster.flavor_id = uuidutils.generate_uuid()
        cluster.default_ng_master = ng_master
        cluster.master_lb_enabled = True
        cluster.master_count = 1
        cluster.keypair = "fake_keypair"
        cluster.fixed_network = None
        cluster.fixed_subnet = None
        cluster.docker_volume_size = None
        cluster.stack_id = uuidutils.generate_uuid()

        return cluster

    def _make_cluster_resource(self, labels=None):
        """Build a ``resources.Cluster`` backed by a mock Magnum cluster."""
        cluster = self._make_magnum_cluster(labels)
        api = self.mocker.Mock()
        pykube_api = self.mocker.Mock()

        return resources.Cluster(
            self.context, api, pykube_api, cluster, namespace="magnum-system"
        )

    @staticmethod
    def _make_existing_capi_cluster(provider):
        """Return a mock that mimics an existing CAPI Cluster object."""
        existing = type("FakeCluster", (), {})()
        existing.obj = {
            "spec": {
                "topology": {
                    "variables": [
                        {
                            "name": "apiServerLoadBalancer",
                            "value": {"enabled": True, "provider": provider},
                        }
                    ]
                }
            }
        }
        return existing

    # ---- Precedence rule 1: label overrides everything ----

    def test_label_sets_provider(self):
        cluster_res = self._make_cluster_resource(labels={"octavia_provider": "ovn"})
        cluster_res.get_or_none = self.mocker.Mock(return_value=None)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "ovn"

    def test_label_overrides_existing_cluster(self):
        existing = self._make_existing_capi_cluster("amphora")
        cluster_res = self._make_cluster_resource(labels={"octavia_provider": "ovn"})
        cluster_res.get_or_none = self.mocker.Mock(return_value=existing)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "ovn"

    # ---- Precedence rule 2: preserve existing provider on upgrade ----

    def test_existing_cluster_provider_preserved(self):
        existing = self._make_existing_capi_cluster("amphora")
        cluster_res = self._make_cluster_resource()
        cluster_res.get_or_none = self.mocker.Mock(return_value=existing)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "amphora"

    def test_existing_cluster_with_ovn_preserved(self):
        existing = self._make_existing_capi_cluster("ovn")
        cluster_res = self._make_cluster_resource()
        cluster_res.get_or_none = self.mocker.Mock(return_value=existing)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "ovn"

    def test_existing_cluster_missing_provider_defaults_to_amphorav2(self):
        """An existing Cluster whose variable has no ``provider`` key."""
        existing = type("FakeCluster", (), {})()
        existing.obj = {
            "spec": {
                "topology": {
                    "variables": [
                        {
                            "name": "apiServerLoadBalancer",
                            "value": {"enabled": True},
                        }
                    ]
                }
            }
        }
        cluster_res = self._make_cluster_resource()
        cluster_res.get_or_none = self.mocker.Mock(return_value=existing)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "amphorav2"

    def test_existing_cluster_missing_lb_variable_defaults_to_amphorav2(self):
        """An existing Cluster that has no apiServerLoadBalancer variable."""
        existing = type("FakeCluster", (), {})()
        existing.obj = {"spec": {"topology": {"variables": []}}}
        cluster_res = self._make_cluster_resource()
        cluster_res.get_or_none = self.mocker.Mock(return_value=existing)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "amphorav2"

    # ---- Precedence rule 3: default for new clusters ----

    def test_new_cluster_defaults_to_amphorav2(self):
        cluster_res = self._make_cluster_resource()
        cluster_res.get_or_none = self.mocker.Mock(return_value=None)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert lb["provider"] == "amphorav2"

    # ---- provider field is always present ----

    def test_provider_always_in_result(self):
        """Ensure ``provider`` is always set regardless of path taken."""
        cluster_res = self._make_cluster_resource()
        cluster_res.get_or_none = self.mocker.Mock(return_value=None)

        obj = cluster_res.get_object()
        lb = _get_api_server_lb_variable(obj)
        assert "provider" in lb
