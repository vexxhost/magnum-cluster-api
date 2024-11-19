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

import re

import pykube
import pytest
import responses
from magnum.objects import fields  # type: ignore
from magnum.tests.unit.objects import utils  # type: ignore
from oslo_serialization import base64, jsonutils  # type: ignore
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
        context,
        mocker,
        auto_scaling_enabled,
        auto_healing_enabled,
        cluster_obj,
    ):
        self.cluster = cluster_obj

        if auto_scaling_enabled is not None:
            self.cluster.labels["auto_scaling_enabled"] = str(auto_scaling_enabled)

        if auto_healing_enabled is not None:
            self.cluster.labels["auto_healing_enabled"] = str(auto_healing_enabled)

        self.node_group = utils.get_test_nodegroup(context, labels={})
        if auto_scaling_enabled is not None:
            self.node_group.min_node_count = 1
            self.node_group.max_node_count = 3
        self.node_group.save = mocker.MagicMock()

        self.server_side_apply_matcher = matchers.query_param_matcher(
            {
                "fieldManager": "atmosphere-operator",
                "force": "True",
            }
        )

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

        match = []
        if method == responses.PATCH:
            match.append(self.server_side_apply_matcher)
            match.append(matchers.json_params_matcher(obj))

        return responses.Response(
            method,
            re.compile(
                f"http://localhost/apis/{objects.Cluster.version}/namespaces/magnum-system/{objects.Cluster.endpoint}/\\w"  # noqa
            ),
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

    def test_create_cluster(
        self,
        requests_mock,
        context,
        ubuntu_driver,
        mock_validate_cluster,
        mock_osc,
        mock_certificates,
        mock_get_server_group,
    ):
        with requests_mock as rsps:
            rsps.add(
                responses.GET,
                re.compile(
                    f"http://localhost/apis/{objects.Cluster.version}/namespaces/magnum-system/{objects.Cluster.endpoint}/\\w+"  # noqa
                ),
                status=404,
            )
            rsps.add_callback(
                responses.PATCH,
                f"http://localhost/api/{pykube.Namespace.version}/{pykube.Namespace.endpoint}/magnum-system",
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/api/{pykube.Secret.version}/namespaces/magnum-system/\\w"
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.KubeadmControlPlaneTemplate.version}/namespaces/magnum-system/{objects.KubeadmControlPlaneTemplate.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.KubeadmConfigTemplate.version}/namespaces/magnum-system/{objects.KubeadmConfigTemplate.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.OpenStackMachineTemplate.version}/namespaces/magnum-system/{objects.OpenStackMachineTemplate.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.OpenStackClusterTemplate.version}/namespaces/magnum-system/{objects.OpenStackClusterTemplate.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.ClusterClass.version}/namespaces/magnum-system/{objects.ClusterClass.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add(
                responses.GET,
                re.compile(
                    f"http://localhost/api/{pykube.Secret.version}/namespaces/magnum-system/\\w"
                ),
                json={
                    "data": {
                        "clouds.yaml": base64.encode_as_text(
                            jsonutils.dumps(
                                {
                                    "clouds": {
                                        "default": {
                                            "region_name": "RegionOne",
                                            "verify": True,
                                            "auth": {
                                                "application_credential_id": "fake_application_credential_id",
                                                "application_credential_secret": "fake_application_credential_secret",
                                            },
                                        }
                                    }
                                }
                            )
                        ),
                    }
                },
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.ClusterResourceSet.version}/namespaces/magnum-system/{objects.ClusterResourceSet.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )
            rsps.add_callback(
                responses.PATCH,
                re.compile(
                    f"http://localhost/apis/{objects.Cluster.version}/namespaces/magnum-system/{objects.Cluster.endpoint}/\\w+"  # noqa
                ),
                match=[self.server_side_apply_matcher],
                callback=lambda request: (200, {}, request.body),
            )

            ubuntu_driver.create_cluster(context, self.cluster, 60)

        assert self.cluster.status == fields.ClusterStatus.CREATE_IN_PROGRESS
        self.cluster.save.assert_called_once()

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

    def test_create_nodegroup(self, context, ubuntu_driver, requests_mock):
        self.cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        self.node_group.status = fields.ClusterStatus.CREATE_IN_PROGRESS

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
        self.cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        self.node_group.status = fields.ClusterStatus.DELETE_IN_PROGRESS

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

        assert self.node_group.status == fields.ClusterStatus.DELETE_IN_PROGRESS
        self.node_group.save.assert_called_once()
