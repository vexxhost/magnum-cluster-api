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

from types import SimpleNamespace

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


def test_cluster_control_plane_labels_match_cloud_controller_manager(
    context, mocker
):
    cluster = mocker.Mock()
    cluster.cluster_template = mocker.Mock(
        network_driver="calico",
        dns_nameserver="1.1.1.1",
        external_network_id="public",
    )
    cluster.default_ng_master = mocker.Mock(image_id="image")
    cluster.docker_volume_size = None
    cluster.fixed_network = None
    cluster.fixed_subnet = None
    cluster.flavor_id = "worker"
    cluster.keypair = None
    cluster.labels = {}
    cluster.master_count = 1
    cluster.master_flavor_id = "control-plane"
    cluster.master_lb_enabled = True
    cluster.nodegroups = []
    cluster.stack_id = "kube-test"

    default_volume_type = SimpleNamespace(name="fast")
    openstack_client = mocker.Mock()
    openstack_client.cinder.return_value.volume_types.default.return_value = (
        default_volume_type
    )
    mocker.patch(
        "magnum_cluster_api.resources.clients.get_openstack_api",
        return_value=openstack_client,
    )
    mocker.patch(
        "magnum_cluster_api.resources.cinder.get_default_boot_volume_type",
        return_value=default_volume_type.name,
    )
    mocker.patch(
        "magnum_cluster_api.resources.generate_machine_deployments_for_cluster",
        return_value=[],
    )
    mocker.patch(
        "magnum_cluster_api.resources.neutron.get_external_network_id",
        return_value="external-network",
    )
    mocker.patch(
        "magnum_cluster_api.resources.neutron.get_fixed_subnet_id",
        return_value=None,
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.ensure_controlplane_server_group",
        return_value="server-group",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.generate_api_cert_san_list",
        return_value="",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.generate_apt_proxy_config",
        return_value="",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.generate_containerd_config",
        return_value="",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.generate_systemd_proxy_config",
        return_value="",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.get_cluster_container_infra_prefix",
        return_value="",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.get_fixed_network_id",
        return_value=None,
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.get_kube_tag",
        return_value="v1.34.3",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.get_operating_system",
        return_value="ubuntu",
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.is_controlplane_different_failure_domain",
        return_value=False,
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.lookup_flavor",
        side_effect=[
            SimpleNamespace(name="control-plane"),
            SimpleNamespace(name="worker"),
        ],
    )
    mocker.patch(
        "magnum_cluster_api.resources.utils.lookup_image",
        return_value={"id": "image"},
    )

    rust_driver = mocker.Mock()
    rust_driver.resolve_immutable_fields.return_value = {
        "apiServerLoadBalancer": {"enabled": True}
    }

    resource = resources.Cluster(
        context,
        mocker.Mock(),
        mocker.Mock(),
        cluster,
        rust_driver,
    ).get_object()

    assert resource["spec"]["topology"]["controlPlane"]["metadata"]["labels"] == {
        "node-role.kubernetes.io/master": "",
        "node-role.kubernetes.io/control-plane": "",
    }


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
