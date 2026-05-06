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
        # mutate_machine_deployment now consults cluster.cluster_template.server_type
        # (via utils.get_default_boot_volume_size) which lazy-loads from the DB
        # in this test context. Stub the helper so existing assertions are
        # unaffected.
        mocker.patch(
            "magnum_cluster_api.utils.get_default_boot_volume_size",
            side_effect=lambda cluster, default: default,
        )
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


def test_mutate_machine_deployment_bm_omits_ephemeral_disk_annotation(context, mocker):
    """For server_type=bm flavors with disk=0 the autoscaler annotation
    should be omitted rather than emitted as "0", which would make the
    autoscaler reject pods that request ephemeral-storage."""
    cluster = utils.get_test_cluster(context, labels={})
    mocker.patch(
        "magnum_cluster_api.utils.get_default_boot_volume_size",
        return_value=0,
    )
    cluster.labels["auto_scaling_enabled"] = "true"
    node_group = utils.get_test_nodegroup(context, labels={})
    node_group.min_node_count = 1
    node_group.max_node_count = 3

    mocker.patch("magnum_cluster_api.utils.lookup_image", return_value={"id": "foo"})
    mocker.patch(
        "magnum_cluster_api.utils.lookup_flavor",
        return_value=flavors.Flavor(
            None,
            {"name": "bm-flavor", "disk": 0, "ram": 4096, "vcpus": 4},
        ),
    )

    md = resources.mutate_machine_deployment(
        context, cluster, node_group, {"name": node_group.name}
    )

    annotations = md["metadata"]["annotations"]
    assert "capacity.cluster-autoscaler.kubernetes.io/ephemeral-disk" not in annotations
    # The other autoscaler hints must still be set so the autoscaler can
    # schedule on cpu/memory.
    assert annotations["capacity.cluster-autoscaler.kubernetes.io/cpu"] == "4"
    assert annotations["capacity.cluster-autoscaler.kubernetes.io/memory"] == "4G"


def test_mutate_machine_deployment_vm_keeps_ephemeral_disk_annotation(context, mocker):
    cluster = utils.get_test_cluster(context, labels={})
    mocker.patch(
        "magnum_cluster_api.utils.get_default_boot_volume_size",
        side_effect=lambda cluster, default: default,
    )
    cluster.labels["auto_scaling_enabled"] = "true"
    node_group = utils.get_test_nodegroup(context, labels={})
    node_group.min_node_count = 1
    node_group.max_node_count = 3

    mocker.patch("magnum_cluster_api.utils.lookup_image", return_value={"id": "foo"})
    mocker.patch(
        "magnum_cluster_api.utils.lookup_flavor",
        return_value=flavors.Flavor(
            None,
            {"name": "vm-flavor", "disk": 20, "ram": 1024, "vcpus": 1},
        ),
    )

    md = resources.mutate_machine_deployment(
        context, cluster, node_group, {"name": node_group.name}
    )

    annotations = md["metadata"]["annotations"]
    assert (
        annotations["capacity.cluster-autoscaler.kubernetes.io/ephemeral-disk"] == "20"
    )
