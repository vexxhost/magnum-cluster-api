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
import responses
from magnum.objects import fields  # type: ignore
from magnum.tests.unit.objects import utils  # type: ignore
from oslo_utils import uuidutils  # type: ignore
from responses import matchers

from magnum_cluster_api import objects, resources


@pytest.mark.parametrize(
    "auto_scaling_enabled", [True, False], ids=lambda x: f"auto_scaling_enabled={x}"
)
@pytest.mark.parametrize(
    "auto_healing_enabled", [True, False], ids=lambda x: f"auto_healing_enabled={x}"
)
class TestDriver:
    @pytest.fixture(autouse=True)
    def setup(
        self,
        auto_scaling_enabled,
        auto_healing_enabled,
        mocker,
        context,
    ):
        self.cluster = utils.get_test_cluster(context, labels={})
        self.cluster.save = mocker.MagicMock()

        if auto_scaling_enabled is not None:
            self.cluster.labels["auto_scaling_enabled"] = str(auto_scaling_enabled)

        if auto_healing_enabled is not None:
            self.cluster.labels["auto_healing_enabled"] = str(auto_healing_enabled)

        self.node_group = utils.get_test_nodegroup(context, labels={})
        if auto_scaling_enabled is not None:
            self.node_group.min_node_count = 1
            self.node_group.max_node_count = 3
        self.node_group.save = mocker.MagicMock()

        mocker.patch(
            "magnum_cluster_api.utils.validate_flavor_name",
            return_value=True,
        )

        mocker.patch(
            "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type",
            return_value="nvme",
        )

        mocker.patch(
            "magnum_cluster_api.utils.get_image_uuid",
            return_value=uuidutils.generate_uuid(),
        )

    def _assert_node_group_status(self, expected_status):
        assert self.node_group.status == expected_status
        self.node_group.save.assert_called_once()

        assert self.cluster.status == fields.ClusterStatus.UPDATE_IN_PROGRESS
        self.cluster.save.assert_called_once()

    def _response_for_cluster_with_machine_deployments(
        self, *machine_deployments, method: str = responses.GET
    ):
        obj = {
            "metadata": {
                "name": self.cluster.stack_id,
                "namespace": "magnum-system",
                "managedFields": None,
            },
            "spec": {
                "topology": {
                    "workers": {
                        "machineDeployments": list(machine_deployments),
                    }
                }
            },
        }

        url = "http://localhost/apis/%s/namespaces/%s/%s/%s" % (
            objects.Cluster.version,
            "magnum-system",
            objects.Cluster.endpoint,
            self.cluster.stack_id,
        )
        match = []
        if method == responses.PATCH:
            url += "?fieldManager=atmosphere-operator&force=True"
            match.append(matchers.json_params_matcher(obj))

        return responses.Response(
            method,
            url,
            json=obj,
            match=match,
        )

    def _response_for_machine_deployment_spec(
        self, machine_deployment_spec=None, deleted=False
    ):
        json = {"items": []}

        if machine_deployment_spec and not deleted:
            json["items"].append(
                {
                    "metadata": {
                        "name": machine_deployment_spec["name"],
                        "namespace": "magnum-system",
                    },
                    "spec": {
                        "replicas": machine_deployment_spec["replicas"],
                        "template": {
                            "metadata": machine_deployment_spec["metadata"],
                        },
                    },
                }
            )

        return responses.Response(
            responses.GET,
            "http://localhost/apis/%s/namespaces/%s/%s"
            % (
                objects.MachineDeployment.version,
                "magnum-system",
                objects.MachineDeployment.endpoint,
            ),
            match=[
                matchers.query_param_matcher(
                    {
                        "labelSelector": "cluster.x-k8s.io/cluster-name=%s,topology.cluster.x-k8s.io/deployment-name=%s"
                        % (self.cluster.stack_id, machine_deployment_spec["name"])
                    }
                ),
            ],
            json=json,
        )

    def setup_node_group_tests(self, rsps, before, after):
        rsps.add(
            self._response_for_cluster_with_machine_deployments(*before),
        )
        rsps.add(
            self._response_for_cluster_with_machine_deployments(
                *after,
                method=responses.PATCH,
            )
        )

        md_found = False
        for md in after:
            if md["name"] == self.node_group.name:
                md_found = True
                rsps.add(
                    self._response_for_machine_deployment_spec(md),
                )
                break

        if not md_found:
            for md in before:
                if md["name"] == self.node_group.name:
                    rsps.add(
                        self._response_for_machine_deployment_spec(md, deleted=True),
                    )
                    break

    def test_create_nodegroup(self, context, ubuntu_driver, requests_mock):
        with requests_mock as rsps:
            self.setup_node_group_tests(
                rsps,
                before=[],
                after=[
                    resources.mutate_machine_deployment(
                        context,
                        self.cluster,
                        self.node_group,
                    ),
                ],
            )

            ubuntu_driver.create_nodegroup(context, self.cluster, self.node_group)

        self._assert_node_group_status(fields.ClusterStatus.CREATE_IN_PROGRESS)

    def test_update_nodegroup(self, context, ubuntu_driver, requests_mock):
        with requests_mock as rsps:
            self.setup_node_group_tests(
                rsps,
                before=[
                    {
                        "name": self.node_group.name,
                    }
                ],
                after=[
                    resources.mutate_machine_deployment(
                        context,
                        self.cluster,
                        self.node_group,
                        {
                            "name": self.node_group.name,
                        },
                    ),
                ],
            )

            ubuntu_driver.update_nodegroup(context, self.cluster, self.node_group)

        self._assert_node_group_status(fields.ClusterStatus.UPDATE_IN_PROGRESS)

    def test_update_nodegroup_with_multiple_node_groups(
        self, context, ubuntu_driver, requests_mock
    ):
        with requests_mock as rsps:
            self.setup_node_group_tests(
                rsps,
                before=[
                    {
                        "name": "unrelated-machine-deployment",
                        "replicas": 1,
                        "metadata": {
                            "annotations": {},
                        },
                    },
                    {
                        "name": self.node_group.name,
                        "replicas": 1,
                        "metadata": {
                            "annotations": {},
                        },
                    },
                ],
                after=[
                    {
                        "name": "unrelated-machine-deployment",
                        "replicas": 1,
                        "metadata": {
                            "annotations": {},
                        },
                    },
                    resources.mutate_machine_deployment(
                        context,
                        self.cluster,
                        self.node_group,
                        {
                            "name": self.node_group.name,
                        },
                    ),
                ],
            )

            ubuntu_driver.update_nodegroup(context, self.cluster, self.node_group)

        self._assert_node_group_status(fields.ClusterStatus.UPDATE_IN_PROGRESS)

    def test_delete_nodegroup_with_multiple_node_groups(
        self, context, ubuntu_driver, requests_mock
    ):
        with requests_mock as rsps:
            self.setup_node_group_tests(
                rsps,
                before=[
                    {
                        "name": "unrelated-machine-deployment",
                        "replicas": 1,
                        "metadata": {
                            "annotations": {},
                        },
                    },
                    {
                        "name": self.node_group.name,
                        "replicas": 1,
                        "metadata": {
                            "annotations": {},
                        },
                    },
                ],
                after=[
                    {
                        "name": "unrelated-machine-deployment",
                        "replicas": 1,
                        "metadata": {
                            "annotations": {},
                        },
                    },
                ],
            )

            ubuntu_driver.delete_nodegroup(context, self.cluster, self.node_group)

        self._assert_node_group_status(fields.ClusterStatus.DELETE_IN_PROGRESS)
