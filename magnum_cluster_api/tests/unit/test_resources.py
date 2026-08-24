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

from magnum_cluster_api import machine_network_profiles, resources


def _machine_network_selection(applies_to="workers"):
    return machine_network_profiles.MachineNetworkSelection(
        name="secondary-network-v1",
        applies_to=applies_to,
        provides_capabilities=(),
        additional_ports=(),
        contract="{}",
        digest="digest",
    )


def test_apply_worker_machine_ports_is_noop_without_profile(mocker):
    machine_deployment = {"variables": {"overrides": [{"name": "flavor"}]}}

    resources.apply_worker_machine_ports(
        machine_deployment, mocker.Mock(name="workers"), None, None
    )

    assert machine_deployment == {"variables": {"overrides": [{"name": "flavor"}]}}


def test_apply_worker_machine_ports_replaces_profile_override(mocker):
    node_group = mocker.Mock()
    node_group.name = "workers"
    machine_deployment = {
        "variables": {
            "overrides": [
                {"name": "flavor", "value": "large"},
                {"name": "workerMachinePorts", "value": ["old"]},
            ]
        }
    }
    ports = [{"nameSuffix": "primary"}, {"nameSuffix": "data"}]

    resources.apply_worker_machine_ports(
        machine_deployment,
        node_group,
        _machine_network_selection(),
        ports,
    )

    assert machine_deployment["variables"]["overrides"] == [
        {"name": "flavor", "value": "large"},
        {"name": "workerMachinePorts", "value": ports},
    ]


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
            assert "replicas" not in md
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

    def test_mutate_machine_deployment_removes_empty_failure_domain(self, context):
        md = resources.mutate_machine_deployment(
            context,
            self.cluster,
            self.node_group,
            {
                "name": self.node_group.name,
                "failureDomain": "",
            },
        )

        assert "failureDomain" not in md

    def test_mutate_machine_deployment_updates_empty_failure_domain(self, context):
        self.node_group.labels["availability_zone"] = "nova"

        md = resources.mutate_machine_deployment(
            context,
            self.cluster,
            self.node_group,
            {
                "name": self.node_group.name,
                "failureDomain": "",
            },
        )

        assert md["failureDomain"] == "nova"


def _patch_new_machine_deployment_dependencies(mocker):
    mocker.patch("magnum_cluster_api.utils.lookup_image", return_value={"id": "foo"})
    mocker.patch(
        "magnum_cluster_api.utils.lookup_flavor",
        return_value=flavors.Flavor(
            None,
            {"name": "bm-flavor", "disk": 0, "ram": 4096, "vcpus": 4},
        ),
    )
    mocker.patch(
        "magnum_cluster_api.integrations.cinder.get_default_boot_volume_type",
        return_value="rbd1",
    )
    mocker.patch(
        "magnum_cluster_api.utils.ensure_worker_server_group",
        return_value="server-group",
    )


def test_new_machine_deployment_omits_unset_failure_domain(context, mocker):
    cluster = utils.get_test_cluster(context, labels={})
    node_group = utils.get_test_nodegroup(context, labels={})
    _patch_new_machine_deployment_dependencies(mocker)

    md = resources.mutate_machine_deployment(context, cluster, node_group)

    assert "failureDomain" not in md


def test_new_machine_deployment_omits_replicas_when_autoscaling_enabled(
    context, mocker
):
    cluster = utils.get_test_cluster(context, labels={"auto_scaling_enabled": "true"})
    node_group = utils.get_test_nodegroup(context, labels={})
    node_group.min_node_count = 1
    node_group.max_node_count = 3
    _patch_new_machine_deployment_dependencies(mocker)

    md = resources.mutate_machine_deployment(context, cluster, node_group)

    assert "replicas" not in md


def test_new_machine_deployment_sets_failure_domain(context, mocker):
    cluster = utils.get_test_cluster(context, labels={})
    node_group = utils.get_test_nodegroup(
        context,
        labels={"availability_zone": "nova"},
    )
    _patch_new_machine_deployment_dependencies(mocker)

    md = resources.mutate_machine_deployment(context, cluster, node_group)

    assert md["failureDomain"] == "nova"


def test_migrate_machineset_failure_domain_removes_empty_value(
    context,
    mocker,
):
    cluster = utils.get_test_cluster(context, labels={})
    node_group = utils.get_test_nodegroup(context, labels={})
    machine_set = mocker.Mock()
    machine_set.obj = {
        "spec": {
            "template": {
                "spec": {
                    "failureDomain": "",
                },
            },
        },
    }
    mocker.patch(
        "magnum_cluster_api.objects.MachineSet.for_node_group",
        return_value=[machine_set],
    )

    resources.migrate_machineset_failure_domain(
        context,
        cluster,
        node_group,
        mocker.Mock(),
    )

    assert "failureDomain" not in machine_set.obj["spec"]["template"]["spec"]
    machine_set.update.assert_called_once_with()


def test_migrate_cluster_failure_domain_removes_empty_value(context, mocker):
    node_group = utils.get_test_nodegroup(context, labels={})
    machine_deployment = {
        "name": node_group.name,
        "failureDomain": "",
    }
    cluster_resource = mocker.Mock()
    cluster_resource.get_machine_deployment_spec.return_value = machine_deployment

    resources.migrate_cluster_failure_domain(node_group, cluster_resource)

    assert "failureDomain" not in machine_deployment
    cluster_resource.set_machine_deployment_spec.assert_called_once_with(
        node_group.name,
        machine_deployment,
    )
    cluster_resource.update.assert_called_once_with()
