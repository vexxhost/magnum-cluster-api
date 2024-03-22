# Copyright (c) 2024 VEXXHOST, Inc.
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

import copy

import pytest
from magnum import objects as magnum_objects  # type: ignore
from magnum.objects import fields  # type: ignore

from magnum_cluster_api import clients, objects, resources


class TestNodeGroupDriver:
    @pytest.fixture(autouse=True)
    def setup(self, cluster):
        self.api = clients.get_pykube_api()
        self.cluster = cluster

    def _assert_machine_deployment_config_matches_node_group(self, md, node_group):
        assert md is not None
        # TODO: more?

    def _assert_machine_deployments_for_node_groups(
        self, *node_groups: magnum_objects.NodeGroup
    ):
        mds = objects.MachineDeployment.objects(
            self.api, namespace="magnum-system"
        ).filter(
            selector={
                "cluster.x-k8s.io/cluster-name": self.cluster.stack_id,
            },
        )

        assert len(mds) == len(
            node_groups
        ), "Expected %d MachineDeployments, got %d" % (
            len(node_groups),
            len(mds),
        )

        # NOTE(mnaser): We need to loop over all the node groups and make sure
        #               that the machine deployments are created for them.
        for ng in node_groups:
            md = resources.get_machine_deployment(self.api, self.cluster, ng)
            self._assert_machine_deployment_config_matches_node_group(md, ng)

        # NOTE(mnaser): We also need to make sure there are no extra machine
        #               deployments created.
        for md in mds:
            assert md.labels["topology.cluster.x-k8s.io/deployment-name"] in [
                ng.name for ng in node_groups
            ]

    def test_default_node_group(self):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)

    def _create_node_group(self, context, driver, node_group_obj, node_group_name):
        new_node_group = copy.deepcopy(node_group_obj)
        new_node_group.name = node_group_name

        driver.create_nodegroup(context, self.cluster, new_node_group)

        assert new_node_group.status == fields.ClusterStatus.CREATE_IN_PROGRESS
        assert new_node_group.save.called_once()

        assert self.cluster.status == fields.ClusterStatus.UPDATE_IN_PROGRESS
        assert self.cluster.save.called_once()

        return new_node_group

    def test_create_node_group(
        self, mock_validate_nodegroup, context, ubuntu_driver, node_group_obj
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-cpu"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            new_node_group,
        )

    def test_create_and_delete_node_group(
        self, mock_validate_nodegroup, context, ubuntu_driver, node_group_obj
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-cpu"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            new_node_group,
        )
        ubuntu_driver.delete_nodegroup(context, self.cluster, new_node_group)
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)

    def test_create_two_node_groups(
        self, mock_validate_nodegroup, context, ubuntu_driver, node_group_obj
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        first_new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-cpu"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        second_new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-memory"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
            second_new_node_group,
        )

    def test_create_and_delete_two_node_groups_deleting_newest_first(
        self, mock_validate_nodegroup, context, ubuntu_driver, node_group_obj
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        first_new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-cpu"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        second_new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-memory"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
            second_new_node_group,
        )
        ubuntu_driver.delete_nodegroup(context, self.cluster, second_new_node_group)
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        ubuntu_driver.delete_nodegroup(context, self.cluster, first_new_node_group)
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)

    def test_create_and_delete_two_node_groups_deleting_oldest_first(
        self, mock_validate_nodegroup, context, ubuntu_driver, node_group_obj
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        first_new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-cpu"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        second_new_node_group = self._create_node_group(
            context, ubuntu_driver, node_group_obj, "high-memory"
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
            second_new_node_group,
        )
        ubuntu_driver.delete_nodegroup(context, self.cluster, first_new_node_group)
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            second_new_node_group,
        )
        ubuntu_driver.delete_nodegroup(context, self.cluster, second_new_node_group)
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
