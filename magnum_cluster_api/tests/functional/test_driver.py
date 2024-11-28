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

from unittest import mock

import pytest
import tenacity
from magnum import objects as magnum_objects  # type: ignore
from magnum.objects import fields  # type: ignore
from magnum.tests.unit.objects import utils  # type: ignore

from magnum_cluster_api import clients, objects


class TestDriver:
    @pytest.fixture(autouse=True)
    def setup(self, cluster):
        self.api = clients.get_pykube_api()
        self.cluster = cluster

    def _assert_machine_deployment_config_matches_node_group(self, md, node_group):
        assert md is not None
        # TODO: more?

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(10),
        wait=tenacity.wait_fixed(1),
    )
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

        worker_ngs = [ng for ng in node_groups if ng.role != "master"]

        assert len(mds) == len(worker_ngs), "Expected %d MachineDeployments, got %d" % (
            len(worker_ngs),
            len(mds),
        )

        # NOTE(mnaser): We need to loop over all the node groups and make sure
        #               that the machine deployments are created for them.
        for ng in worker_ngs:
            md = objects.MachineDeployment.for_node_group(self.api, self.cluster, ng)
            self._assert_machine_deployment_config_matches_node_group(md, ng)

        # NOTE(mnaser): We also need to make sure there are no extra machine
        #               deployments created.
        for md in mds:
            assert md.labels["topology.cluster.x-k8s.io/deployment-name"] in [
                ng.name for ng in node_groups
            ]

    def test_default_node_group(self):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)

    def _create_node_group(self, context, driver, node_group_name, cluster_template):
        new_node_group = utils.get_test_nodegroup(
            context,
            name="default-worker",
            role="worker",
            node_count=1,
            flavor_id=cluster_template.master_flavor_id,
            image_id=cluster_template.image_id,
            labels={},
            status=fields.ClusterStatus.CREATE_IN_PROGRESS,
        )
        new_node_group.name = node_group_name
        new_node_group.save = mock.MagicMock()

        self.cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        driver.create_nodegroup(context, self.cluster, new_node_group)

        return new_node_group

    def test_upgrade_cluster(self, context, ubuntu_driver, cluster_template):
        cluster_template.labels["kube_tag"] = "v1.26.3"

        cluster_resource = objects.Cluster.for_magnum_cluster(self.api, self.cluster)
        current_observed_generation = cluster_resource.observed_generation

        ubuntu_driver.upgrade_cluster(
            context, self.cluster, cluster_template, None, None
        )

        cluster_resource.wait_for_observed_generation_changed(
            existing_observed_generation=current_observed_generation,
        )

        cluster_resource = objects.Cluster.for_magnum_cluster(self.api, self.cluster)
        assert cluster_resource.observed_generation != current_observed_generation

        self.cluster.save.assert_not_called()

    def test_upgrade_cluster_to_same_version(
        self, kube_tag, context, ubuntu_driver, cluster_template
    ):
        cluster_template.labels["kube_tag"] = kube_tag

        cluster_resource = objects.Cluster.for_magnum_cluster(self.api, self.cluster)
        current_observed_generation = cluster_resource.observed_generation

        ubuntu_driver.upgrade_cluster(
            context, self.cluster, cluster_template, None, None
        )

        cluster_resource = objects.Cluster.for_magnum_cluster(self.api, self.cluster)
        assert cluster_resource.observed_generation == current_observed_generation

        self.cluster.save.assert_not_called()

    def test_upgrade_cluster_with_multiple_node_groups(
        self,
        mocker,
        control_plane_node_group_obj,
        worker_node_group_obj,
        mock_validate_nodegroup,
        context,
        ubuntu_driver,
        cluster_template,
    ):
        new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-cpu", cluster_template
        )

        mocker.patch(
            "magnum.objects.NodeGroup.list",
            return_value=[
                control_plane_node_group_obj,
                worker_node_group_obj,
                new_node_group,
            ],
        )

        cluster_template.labels["kube_tag"] = "v1.26.3"

        cluster_resource = objects.Cluster.for_magnum_cluster(self.api, self.cluster)
        current_observed_generation = cluster_resource.observed_generation

        ubuntu_driver.upgrade_cluster(
            context, self.cluster, cluster_template, None, None
        )

        cluster_resource = objects.Cluster.for_magnum_cluster(self.api, self.cluster)
        assert cluster_resource.observed_generation != current_observed_generation

        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
        )

        self.cluster.save.assert_not_called()

    def test_create_node_group(
        self, mock_validate_nodegroup, context, ubuntu_driver, cluster_template
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-cpu", cluster_template
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            new_node_group,
        )

    def test_create_and_delete_node_group(
        self, mock_validate_nodegroup, context, ubuntu_driver, cluster_template
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-cpu", cluster_template
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            new_node_group,
        )
        ubuntu_driver.delete_nodegroup(context, self.cluster, new_node_group)
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)

    def test_create_two_node_groups(
        self, mock_validate_nodegroup, context, ubuntu_driver, cluster_template
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        first_new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-cpu", cluster_template
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        second_new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-memory", cluster_template
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
            second_new_node_group,
        )

    def test_create_and_delete_two_node_groups_deleting_newest_first(
        self, mock_validate_nodegroup, context, ubuntu_driver, cluster_template
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        first_new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-cpu", cluster_template
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        second_new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-memory", cluster_template
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
        self, mock_validate_nodegroup, context, ubuntu_driver, cluster_template
    ):
        self._assert_machine_deployments_for_node_groups(*self.cluster.nodegroups)
        first_new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-cpu", cluster_template
        )
        self._assert_machine_deployments_for_node_groups(
            *self.cluster.nodegroups,
            first_new_node_group,
        )
        second_new_node_group = self._create_node_group(
            context, ubuntu_driver, "high-memory", cluster_template
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
