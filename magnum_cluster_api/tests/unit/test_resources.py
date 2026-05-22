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


def _variables_by_name(variables):
    return {item["name"]: item["value"] for item in variables}


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


def test_mutate_machine_deployment_normalizes_null_hardware_disk_bus(context, mocker):
    cluster = utils.get_test_cluster(context, labels={})
    node_group = utils.get_test_nodegroup(
        context,
        labels={},
        name="default-worker",
        role="worker",
        status=fields.ClusterStatus.CREATE_IN_PROGRESS,
    )

    mocker.patch("magnum_cluster_api.clients.get_openstack_api")
    mocker.patch(
        "magnum_cluster_api.utils.lookup_flavor",
        return_value=flavors.Flavor(
            None,
            {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1},
        ),
    )
    mocker.patch(
        "magnum_cluster_api.utils.lookup_image",
        return_value={"id": "fake-image", "hw_disk_bus": None},
    )
    mocker.patch(
        "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type",
        return_value="fake-volume-type",
    )
    mocker.patch(
        "magnum_cluster_api.utils.ensure_worker_server_group",
        return_value="fake-server-group",
    )

    machine_deployment = resources.mutate_machine_deployment(
        context, cluster, node_group
    )

    variables = _variables_by_name(
        machine_deployment["variables"]["overrides"],
    )
    assert variables["hardwareDiskBus"] == ""


def test_cluster_object_normalizes_null_hardware_disk_bus(
    context, cluster_obj, pykube_api, mock_rust_driver, mocker
):
    mocker.patch("magnum_cluster_api.clients.get_openstack_api")
    mocker.patch(
        "magnum_cluster_api.utils.lookup_flavor",
        return_value=flavors.Flavor(
            None,
            {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1},
        ),
    )
    mocker.patch(
        "magnum_cluster_api.utils.lookup_image",
        return_value={"id": "fake-image", "hw_disk_bus": None},
    )
    default_volume_type = mocker.Mock()
    default_volume_type.name = "fake-volume-type"
    mocker.patch(
        "magnum_cluster_api.integrations.cinder.get_default_volume_type",
        return_value=default_volume_type,
    )
    mocker.patch(
        "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type",
        return_value="fake-boot-volume-type",
    )
    mocker.patch(
        "magnum_cluster_api.utils.get_external_network_id",
        return_value="fake-external-network",
    )
    mocker.patch(
        "magnum_cluster_api.utils.get_fixed_subnet_id",
        return_value="fake-fixed-subnet",
    )
    mocker.patch(
        "magnum_cluster_api.utils.get_fixed_network_id",
        return_value="fake-fixed-network",
    )
    mocker.patch(
        "magnum_cluster_api.utils.ensure_controlplane_server_group",
        return_value="fake-control-plane-server-group",
    )
    mocker.patch(
        "magnum_cluster_api.utils.ensure_worker_server_group",
        return_value="fake-worker-server-group",
    )

    cluster = resources.Cluster(
        context,
        mocker.Mock(),
        pykube_api,
        cluster_obj,
        rust_driver=mock_rust_driver,
    )

    cluster_object = cluster.get_object()
    variables = _variables_by_name(cluster_object["spec"]["topology"]["variables"])
    machine_deployment_variables = _variables_by_name(
        cluster_object["spec"]["topology"]["workers"]["machineDeployments"][0][
            "variables"
        ]["overrides"]
    )

    assert variables["hardwareDiskBus"] == ""
    assert machine_deployment_variables["hardwareDiskBus"] == ""


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
