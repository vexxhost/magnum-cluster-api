# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

import string

import fixtures  # type: ignore
import shortuuid
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import context as magnum_context  # type: ignore
from magnum.tests.unit.db import utils  # type: ignore
from novaclient.v2 import flavors  # type: ignore
from oslo_utils import uuidutils  # type: ignore
from oslotest import base  # type: ignore
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_fixed

from magnum_cluster_api import (
    clients,
    exceptions,
    magnum_cluster_api,
    objects,
    resources,
)
from magnum_cluster_api.tests.functional import fixtures as mcapi_fixtures


class NodeGroups(fixtures.Fixture):
    def __init__(self, context: magnum_context.RequestContext):
        super(NodeGroups, self).__init__()
        self.context = context

    def _setUp(self):
        self.nodegroup_list = self.useFixture(
            fixtures.MockPatch("magnum.objects.nodegroup.NodeGroup.list")
        ).mock

        nodegroups = utils.get_nodegroups_for_cluster()

        nodegroups["master"]["labels"] = {}
        nodegroups["master"]["flavor_id"] = uuidutils.generate_uuid()

        nodegroups["worker"]["labels"] = {}
        nodegroups["worker"]["flavor_id"] = uuidutils.generate_uuid()

        self.nodegroup_list.return_value = [
            magnum_objects.NodeGroup(self.context, **nodegroups["master"]),
            magnum_objects.NodeGroup(self.context, **nodegroups["worker"]),
        ]


class ResourceBaseTestCase(base.BaseTestCase):
    def setUp(self):
        super(ResourceBaseTestCase, self).setUp()

        self.context = magnum_context.RequestContext(is_admin=False)

        self.mock_cinder = self.useFixture(
            fixtures.MockPatch("magnum_cluster_api.clients.OpenStackClients.cinder")
        ).mock
        self.mock_cinder.return_value.volume_types.default.return_value.name = (
            "fake-boot-volume-type"
        )

        self.useFixture(NodeGroups(self.context))

        self.useFixture(
            fixtures.MockPatch(
                "magnum_cluster_api.utils.generate_cloud_controller_manager_config",
                return_value="fake-config",
            )
        )
        self.useFixture(
            fixtures.MockPatch(
                "magnum_cluster_api.utils.lookup_flavor",
                return_value=flavors.Flavor(
                    None,
                    {
                        "name": "fake-flavor",
                        "disk": 10,
                        "ram": 1024,
                        "vcpus": 1,
                    },
                ),
            )
        )
        self.useFixture(
            fixtures.MockPatch(
                "magnum_cluster_api.utils.lookup_image",
                return_value={"id": uuidutils.generate_uuid()},
            )
        )
        self.useFixture(
            fixtures.MockPatch(
                "magnum_cluster_api.utils.ensure_controlplane_server_group",
                return_value=uuidutils.generate_uuid(),
            )
        )
        self.useFixture(
            fixtures.MockPatch(
                "magnum_cluster_api.utils.ensure_worker_server_group",
                return_value=uuidutils.generate_uuid(),
            )
        )

        self.api = magnum_cluster_api.KubeClient()
        self.pykube_api = clients.get_pykube_api()

        alphabet = string.ascii_lowercase + string.digits
        su = shortuuid.ShortUUID(alphabet=alphabet)

        self.namespace_name = "test-%s" % (su.random(length=5))
        self.namespace = self.api.create_or_update(
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {
                    "name": self.namespace_name,
                },
            }
        )
        self.addCleanup(self.api.delete, "v1", "Namespace", self.namespace_name)


class TestClusterClass(ResourceBaseTestCase):
    def _test_disable_api_server_floating_ip(
        self,
        master_lb_floating_ip_enabled: bool | None,
        expected: bool,
    ):
        cluster = magnum_objects.Cluster(
            self.context,
            **utils.get_test_cluster(
                master_flavor_id="m1.medium",
                flavor_id="m1.large",
                keypair="fake-keypair",
                labels={},
            ),
        )
        cluster.cluster_template = magnum_objects.ClusterTemplate(
            self.context,
            **utils.get_test_cluster_template(
                cluster_distro="ubuntu",
            ),
        )

        if master_lb_floating_ip_enabled is not None:
            cluster.labels["master_lb_floating_ip_enabled"] = str(
                master_lb_floating_ip_enabled
            )

        capi_cluster: resources.Cluster = self.useFixture(
            mcapi_fixtures.ClusterFixture(
                self.context,
                self.api,
                self.pykube_api,
                self.namespace_name,
                cluster,
            )
        ).cluster

        capi_cluster_obj = capi_cluster.get_resource()
        capi_cluster_variables = {
            item["name"]: item["value"]
            for item in capi_cluster_obj["spec"]["topology"]["variables"]
        }

        self.assertIn("disableAPIServerFloatingIP", capi_cluster_variables)
        self.assertEquals(
            expected, capi_cluster_variables.get("disableAPIServerFloatingIP")
        )

        @retry(
            stop=stop_after_delay(10),
            wait=wait_fixed(1),
            retry=retry_if_exception_type(exceptions.OpenStackClusterNotCreated),
        )
        def get_capi_oc():
            filtered_clusters = (
                objects.OpenStackCluster.objects(
                    self.pykube_api,
                    namespace=self.namespace_name,
                )
                .filter(selector={"cluster.x-k8s.io/cluster-name": capi_cluster.name})
                .all()
            )

            if len(filtered_clusters) == 0:
                raise exceptions.OpenStackClusterNotCreated()

            return list(filtered_clusters)[0]

        capi_oc = get_capi_oc()
        self.assertEqual(
            expected, capi_oc.obj["spec"].get("disableAPIServerFloatingIP", False)
        )

    def test_disable_api_server_floating_ip_unset(self):
        self._test_disable_api_server_floating_ip(
            master_lb_floating_ip_enabled=None, expected=False
        )

    def test_disable_api_server_floating_ip_true(self):
        self._test_disable_api_server_floating_ip(
            master_lb_floating_ip_enabled=True, expected=False
        )

    def test_disable_api_server_floating_ip_false(self):
        self._test_disable_api_server_floating_ip(
            master_lb_floating_ip_enabled=False, expected=True
        )
