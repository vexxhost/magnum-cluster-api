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

import pytest
from magnum.objects import fields
from magnum.tests.unit.objects import utils


class TestDriver:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, context, mock_pykube, mock_validate_nodegroup):
        self.cluster = utils.get_test_cluster(context, labels={})
        self.cluster.save = mocker.MagicMock()

        self.node_group = utils.get_test_nodegroup(context)
        self.node_group.save = mocker.MagicMock()

        self.mock_cluster_resource = mocker.MagicMock()
        self.mock_cluster_objects = mocker.patch(
            "magnum_cluster_api.objects.Cluster.objects"
        )
        self.mock_cluster_objects.return_value.get.return_value = (
            self.mock_cluster_resource
        )

        self.mock_wait_capi_cluster_reconciliation_start = mocker.patch(
            "magnum_cluster_api.driver.BaseDriver.wait_capi_cluster_reconciliation_start"
        )

    def _assert_node_group_crud_calls(self):
        self.mock_cluster_objects.return_value.get.assert_called_once_with(
            name=self.cluster.stack_id
        )
        self.mock_cluster_resource.update.assert_called_once()
        self.mock_wait_capi_cluster_reconciliation_start.assert_called_once()

    def _assert_node_group_status(self, expected_status):
        assert self.node_group.status == expected_status
        self.node_group.save.assert_called_once()

        assert self.cluster.status == fields.ClusterStatus.UPDATE_IN_PROGRESS
        self.cluster.save.assert_called_once()

    def test_create_nodegroup(self, mocker, context, ubuntu_driver):
        self.mock_cluster_resource.obj = {
            "spec": {
                "topology": {
                    "workers": {
                        "machineDeployments": [],
                    }
                }
            },
        }

        mock_mutate_machine_deployment = mocker.patch(
            "magnum_cluster_api.resources.mutate_machine_deployment"
        )

        ubuntu_driver.create_nodegroup(context, self.cluster, self.node_group)

        mock_mutate_machine_deployment.assert_called_once_with(
            context, self.cluster, self.node_group
        )

        assert self.mock_cluster_resource.obj["spec"]["topology"]["workers"][
            "machineDeployments"
        ] == [mock_mutate_machine_deployment.return_value]

        self._assert_node_group_crud_calls()
        self._assert_node_group_status(fields.ClusterStatus.CREATE_IN_PROGRESS)

    def test_update_nodegroup(self, mocker, context, ubuntu_driver):
        self.mock_cluster_resource.obj = {
            "spec": {
                "topology": {
                    "workers": {
                        "machineDeployments": [
                            {
                                "name": self.node_group.name,
                            }
                        ],
                    }
                }
            },
        }

        mock_mutate_machine_deployment = mocker.patch(
            "magnum_cluster_api.resources.mutate_machine_deployment"
        )

        ubuntu_driver.update_nodegroup(context, self.cluster, self.node_group)

        mock_mutate_machine_deployment.assert_called_once_with(
            context,
            self.cluster,
            self.node_group,
            {
                "name": self.node_group.name,
            },
        )

        assert self.mock_cluster_resource.obj["spec"]["topology"]["workers"][
            "machineDeployments"
        ] == [mock_mutate_machine_deployment.return_value]

        self._assert_node_group_crud_calls()
        self._assert_node_group_status(fields.ClusterStatus.UPDATE_IN_PROGRESS)

    def test_update_nodegroup_with_multiple_node_groups(
        self, mocker, context, ubuntu_driver
    ):
        mock_machine_deployment = mocker.MagicMock()

        self.mock_cluster_resource.obj = {
            "spec": {
                "topology": {
                    "workers": {
                        "machineDeployments": [
                            mock_machine_deployment,
                            {
                                "name": self.node_group.name,
                            },
                        ],
                    }
                }
            },
        }

        mock_mutate_machine_deployment = mocker.patch(
            "magnum_cluster_api.resources.mutate_machine_deployment"
        )

        ubuntu_driver.update_nodegroup(context, self.cluster, self.node_group)

        assert not mock_machine_deployment.called

        mock_mutate_machine_deployment.assert_called_once_with(
            context,
            self.cluster,
            self.node_group,
            {
                "name": self.node_group.name,
            },
        )

        assert self.mock_cluster_resource.obj["spec"]["topology"]["workers"][
            "machineDeployments"
        ] == [
            mock_machine_deployment,
            mock_mutate_machine_deployment.return_value,
        ]

        self._assert_node_group_crud_calls()
        self._assert_node_group_status(fields.ClusterStatus.UPDATE_IN_PROGRESS)

    def test_delete_nodegroup_with_multiple_node_groups(
        self, mocker, context, ubuntu_driver
    ):
        mock_machine_deployment = mocker.MagicMock()

        self.mock_cluster_resource.obj = {
            "spec": {
                "topology": {
                    "workers": {
                        "machineDeployments": [
                            mock_machine_deployment,
                            {
                                "name": self.node_group.name,
                            },
                        ],
                    }
                }
            },
        }

        ubuntu_driver.delete_nodegroup(context, self.cluster, self.node_group)

        assert not mock_machine_deployment.called

        assert self.mock_cluster_resource.obj["spec"]["topology"]["workers"][
            "machineDeployments"
        ] == [
            mock_machine_deployment,
        ]

        self._assert_node_group_crud_calls()
        self._assert_node_group_status(fields.ClusterStatus.DELETE_IN_PROGRESS)
