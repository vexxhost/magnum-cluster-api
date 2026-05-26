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
from unittest import mock

import openstack
import pykube
import pytest
import responses
from heatclient import exc  # type: ignore
from magnum.objects import fields  # type: ignore
from magnum.tests.unit.objects import utils  # type: ignore
from novaclient.v2 import flavors  # type: ignore
from oslo_serialization import base64, jsonutils  # type: ignore
from oslo_utils import uuidutils  # type: ignore
from responses import matchers

from magnum_cluster_api import driver, exceptions, objects, resources


def test_create_cluster_validates_quota_before_creating_capi_resources(context, mocker):
    cluster = mocker.Mock()
    cluster.save = mocker.Mock()

    ubuntu_driver = driver.UbuntuDriver.__new__(driver.UbuntuDriver)
    ubuntu_driver.k8s_api = mocker.Mock()
    ubuntu_driver.rust_driver = mocker.Mock()
    ubuntu_driver._create_cluster = mocker.Mock(return_value="created")

    order = []
    mocker.patch(
        "magnum_cluster_api.utils.generate_cluster_api_name",
        return_value="kube-test",
    )
    mocker.patch(
        "magnum_cluster_api.utils.validate_cluster",
        side_effect=lambda *_args: order.append("validate_cluster"),
    )
    mocker.patch(
        "magnum_cluster_api.utils.validate_cluster_server_group_members_quota",
        side_effect=lambda *_args: order.append("validate_quota"),
    )
    ubuntu_driver.rust_driver.create_cluster.side_effect = lambda *_args: order.append(
        "create_capi_resources"
    )
    ubuntu_driver._create_cluster.side_effect = lambda *_args: order.append(
        "create_openstack_resources"
    )

    ubuntu_driver.create_cluster(context, cluster, 60)

    assert cluster.stack_id == "kube-test"
    assert order == [
        "validate_cluster",
        "validate_quota",
        "create_capi_resources",
        "create_openstack_resources",
    ]


def test_create_cluster_stops_before_capi_resources_when_quota_exceeded(
    context, mocker
):
    cluster = mocker.Mock()
    cluster.save = mocker.Mock()

    ubuntu_driver = driver.UbuntuDriver.__new__(driver.UbuntuDriver)
    ubuntu_driver.k8s_api = mocker.Mock()
    ubuntu_driver.rust_driver = mocker.Mock()
    ubuntu_driver._create_cluster = mocker.Mock()

    mocker.patch(
        "magnum_cluster_api.utils.generate_cluster_api_name",
        return_value="kube-test",
    )
    mocker.patch("magnum_cluster_api.utils.validate_cluster")
    mocker.patch(
        "magnum_cluster_api.utils.validate_cluster_server_group_members_quota",
        side_effect=exceptions.ServerGroupMembersQuotaExceeded(
            server_group_name="kube-test-default-worker",
            requested=3,
            limit=2,
        ),
    )

    with pytest.raises(exceptions.ServerGroupMembersQuotaExceeded):
        ubuntu_driver.create_cluster(context, cluster, 60)

    ubuntu_driver.rust_driver.create_cluster.assert_not_called()
    ubuntu_driver._create_cluster.assert_not_called()


def test_create_nodegroup_validates_quota_before_creating_server_group(context, mocker):
    cluster = mocker.Mock()
    cluster.uuid = "cluster-test"
    nodegroup = mocker.Mock()

    ubuntu_driver = driver.UbuntuDriver.__new__(driver.UbuntuDriver)
    ubuntu_driver.k8s_api = mocker.Mock()

    cluster_resource = mocker.Mock()
    cluster_resource.obj = {
        "spec": {"topology": {"workers": {"machineDeployments": []}}},
    }
    mocker.patch(
        "magnum_cluster_api.objects.Cluster.for_magnum_cluster",
        return_value=cluster_resource,
    )
    mocker.patch(
        "magnum_cluster_api.resources.mutate_machine_deployment",
        return_value={"name": "default-worker"},
    )
    mocker.patch("magnum_cluster_api.utils.kube_apply_patch")
    mocker.patch("magnum_cluster_api.utils.validate_nodegroup")

    order = []
    mocker.patch(
        "magnum_cluster_api.utils.validate_nodegroup_server_group_members_quota",
        side_effect=lambda *_args: order.append("validate_quota"),
    )
    mocker.patch(
        "magnum_cluster_api.utils.ensure_worker_server_group",
        side_effect=lambda **_kwargs: order.append("ensure_server_group"),
    )
    mocker.patch("magnum_cluster_api.sync.ClusterLock.acquire")
    mocker.patch("magnum_cluster_api.sync.ClusterLock.release")

    ubuntu_driver.create_nodegroup(context, cluster, nodegroup)

    assert order == ["validate_quota", "ensure_server_group"]


def test_resize_cluster_validates_worker_quota_before_updating_nodegroup(
    context, mocker
):
    cluster = mocker.Mock()
    cluster.uuid = "cluster-test"
    nodegroup = mocker.Mock()
    nodegroup.role = "worker"

    ubuntu_driver = driver.UbuntuDriver.__new__(driver.UbuntuDriver)

    order = []
    mocker.patch("magnum_cluster_api.utils.validate_cluster")
    mocker.patch(
        "magnum_cluster_api.utils.validate_nodegroup_server_group_members_quota",
        side_effect=lambda *_args: order.append("validate_quota"),
    )
    ubuntu_driver._update_nodegroup = mocker.Mock(
        side_effect=lambda *_args: order.append("update_nodegroup")
    )
    mocker.patch("magnum_cluster_api.sync.ClusterLock.acquire")
    mocker.patch("magnum_cluster_api.sync.ClusterLock.release")

    ubuntu_driver.resize_cluster(context, cluster, None, 3, [], nodegroup)

    assert order == ["validate_quota", "update_nodegroup"]


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

        self.node_group = utils.get_test_nodegroup(
            context, labels={}, name="default-worker"
        )
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
            "magnum_cluster_api.utils.lookup_flavor",
            return_value=flavors.Flavor(
                None,
                {"name": "fake-flavor", "disk": 10, "ram": 1024, "vcpus": 1},
            ),
        )

        mocker.patch(
            "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type",
            return_value="nvme",
        )

        mocker.patch(
            "magnum_cluster_api.utils.lookup_image",
            return_value={"id": uuidutils.generate_uuid()},
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

    def _response_for_openstack_machines(self, deployment_name, machine_specs=None):
        """Helper method to create a mock response for OpenStackMachine API calls."""
        json = {"items": []}

        if machine_specs:
            for spec in machine_specs:
                json["items"].append(
                    {
                        "metadata": {
                            "name": spec.get("name", "test-machine"),
                            "namespace": "magnum-system",
                        },
                        "spec": {
                            "image": {"id": spec.get("image_id", "test-image-id")},
                            "flavor": spec.get("flavor", "test-flavor"),
                        },
                    }
                )

        return responses.Response(
            responses.GET,
            "http://localhost/apis/%s/namespaces/%s/%s"
            % (
                objects.OpenStackMachine.version,
                "magnum-system",
                objects.OpenStackMachine.endpoint,
            ),
            match=[
                matchers.query_param_matcher(
                    {
                        "labelSelector": "cluster.x-k8s.io/cluster-name=%s,topology.cluster.x-k8s.io/deployment-name=%s"
                        % (self.cluster.stack_id, deployment_name)
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
        mock_rust_driver,
    ):
        ubuntu_driver._kube_client = mock.MagicMock()

        with requests_mock as rsps:
            rsps.add(
                responses.GET,
                re.compile(
                    f"http://localhost/apis/{objects.Cluster.version}/namespaces/magnum-system/{objects.Cluster.endpoint}/\\w+"  # noqa
                ),
                status=404,
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

            ubuntu_driver.create_cluster(context, self.cluster, 60)

            assert ubuntu_driver._kube_client.create_or_update.call_args_list == [
                mock.call(
                    resources.CloudConfigSecret(
                        context,
                        ubuntu_driver._kube_client,
                        self.cluster,
                        "RegionOne",
                        openstack.identity.v3.application_credential.ApplicationCredential(
                            id="fake_id", secret="fake_secret"
                        ),
                    ).get_resource()
                ),
                mock.call(
                    resources.ApiCertificateAuthoritySecret(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                    ).get_resource()
                ),
                mock.call(
                    resources.EtcdCertificateAuthoritySecret(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                    ).get_resource()
                ),
                mock.call(
                    resources.FrontProxyCertificateAuthoritySecret(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                    ).get_resource()
                ),
                mock.call(
                    resources.ServiceAccountCertificateAuthoritySecret(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                    ).get_resource()
                ),
                mock.call(
                    resources.LegacyClusterResourcesSecret(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                    ).get_resource()
                ),
                mock.call(
                    resources.CloudProviderClusterResourcesSecret(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                    ).get_resource()
                ),
                mock.call(
                    resources.Cluster(
                        context,
                        ubuntu_driver._kube_client,
                        ubuntu_driver.k8s_api,
                        self.cluster,
                        rust_driver=ubuntu_driver.rust_driver,
                    ).get_resource()
                ),
            ]

        assert self.cluster.status == fields.ClusterStatus.CREATE_IN_PROGRESS
        self.cluster.save.assert_called_once()

        assert self.cluster.status == fields.ClusterStatus.CREATE_IN_PROGRESS
        self.cluster.save.assert_called_once()

    def setup_node_group_tests(self, rsps, before, after=None):
        rsps.add(
            self._response_for_cluster_with_machine_deployments(*before),
        )
        if after:
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

    def test_delete_missing_nodegroup(self, context, ubuntu_driver, requests_mock):
        self.cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS

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
                    }
                ],
            )

            with pytest.raises(exc.HTTPNotFound):
                ubuntu_driver.delete_nodegroup(context, self.cluster, self.node_group)

    def test_update_nodegroups_status_delete_complete(
        self, context, ubuntu_driver, requests_mock
    ):
        """Test that nodegroups in DELETE_COMPLETE status are properly destroyed."""
        self.cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        self.node_group.status = fields.ClusterStatus.DELETE_COMPLETE
        self.node_group.is_default = False
        self.node_group.destroy = mock.MagicMock()

        with mock.patch(
            "magnum.objects.NodeGroup.list", return_value=[self.node_group]
        ):
            with requests_mock as rsps:
                rsps.add(
                    self._response_for_cluster_with_machine_deployments(
                        {
                            "name": self.node_group.name,
                            "replicas": 1,
                            "metadata": {"labels": {}},
                            "variables": {
                                "overrides": [
                                    {"name": "flavor", "value": "test-flavor"},
                                    {"name": "imageUUID", "value": "test-image-id"},
                                ]
                            },
                        }
                    )
                )

                ubuntu_driver.update_nodegroups_status(context, self.cluster)

                # Verify the nodegroup was destroyed
                self.node_group.destroy.assert_called_once()

    @pytest.mark.parametrize(
        "cluster_status,should_destroy",
        [
            (fields.ClusterStatus.UPDATE_IN_PROGRESS, False),
            (fields.ClusterStatus.DELETE_IN_PROGRESS, True),
        ],
    )
    def test_update_nodegroups_status_delete_complete_default_nodegroup(
        self, context, ubuntu_driver, requests_mock, cluster_status, should_destroy
    ):

        self.cluster.status = cluster_status
        self.node_group.status = fields.ClusterStatus.DELETE_COMPLETE
        self.node_group.is_default = True
        self.node_group.destroy = mock.MagicMock()

        with mock.patch(
            "magnum.objects.NodeGroup.list", return_value=[self.node_group]
        ):
            with requests_mock as rsps:
                rsps.add(
                    self._response_for_cluster_with_machine_deployments(
                        {
                            "name": "default-worker",
                            "replicas": 1,
                            "metadata": {"labels": {}},
                            "variables": {
                                "overrides": [
                                    {"name": "flavor", "value": "test-flavor"},
                                    {"name": "imageUUID", "value": "test-image-id"},
                                ]
                            },
                        }
                    )
                )

                ubuntu_driver.update_nodegroups_status(context, self.cluster)

                if should_destroy:
                    self.node_group.destroy.assert_called_once()
                else:
                    self.node_group.destroy.assert_not_called()
