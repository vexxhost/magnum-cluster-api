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

    mock_get_image_uuid = mocker.patch("magnum_cluster_api.utils.get_image_uuid")
    mock_get_image_uuid.return_value = "foo"

    mds = resources.generate_machine_deployments_for_cluster(
        context,
        cluster,
    )

    assert len(mds) == 2


class TestExistingMutateMachineDeployment:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, context):
        self.cluster = utils.get_test_cluster(context)
        self.node_group = utils.get_test_nodegroup(context)

        self.mock_get_node_group_label = mocker.patch(
            "magnum_cluster_api.utils.get_node_group_label"
        )
        self.mock_auto_scaling = mocker.patch(
            "magnum_cluster_api.utils.get_auto_scaling_enabled"
        )
        self.mock_get_node_group_min_node_count = mocker.patch(
            "magnum_cluster_api.utils.get_node_group_min_node_count"
        )
        self.mock_get_node_group_max_node_count = mocker.patch(
            "magnum_cluster_api.utils.get_node_group_max_node_count"
        )

    def _assert_no_mutations(self, md):
        assert md["name"] == self.node_group.name
        assert "class" not in md
        self.mock_get_node_group_label.assert_not_called()

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

    def test_mutate_machine_deployment_without_autoscaling(self, context):
        self.mock_auto_scaling.return_value = False

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

        assert md["replicas"] == self.node_group.node_count
        assert md["metadata"]["annotations"] == {}

    def test_mutate_machine_deployment_with_autoscaling(self, context):
        self.mock_auto_scaling.return_value = True

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

        assert md["replicas"] is None
        assert md["metadata"]["annotations"][resources.AUTOSCALE_ANNOTATION_MIN] == str(
            self.mock_get_node_group_min_node_count.return_value
        )
        assert md["metadata"]["annotations"][resources.AUTOSCALE_ANNOTATION_MAX] == str(
            self.mock_get_node_group_max_node_count.return_value
        )
