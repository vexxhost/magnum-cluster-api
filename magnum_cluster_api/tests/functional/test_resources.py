# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

import string

import fixtures  # type: ignore
import shortuuid
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import context as magnum_context  # type: ignore
from magnum.tests.unit.db import utils  # type: ignore
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
                "magnum_cluster_api.utils.get_image_uuid",
                return_value=uuidutils.generate_uuid(),
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
        name = "test-%s" % (su.random(length=5))

        self.namespace = resources.Namespace(self.api, name)
        self.namespace.apply()
        self.addCleanup(self.namespace.delete)


class TestClusterClass(ResourceBaseTestCase):
    def setUp(self):
        super(TestClusterClass, self).setUp()
        resources.create_cluster_class(self.api, namespace=self.namespace.name)

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
            **utils.get_test_cluster_template(),
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
                self.namespace,
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
                    namespace=self.namespace.name,
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


class TestClusterVariableManipulation(ResourceBaseTestCase):
    def setUp(self):
        super(TestClusterVariableManipulation, self).setUp()

        self.cluster_class_original = resources.create_cluster_class(
            self.api, namespace=self.namespace.name
        )

        cc = objects.ClusterClass.objects(
            self.pykube_api, namespace=self.namespace.name
        ).get(name=resources.CLUSTER_CLASS_NAME)

        self.assertNotIn("extraTestVariable", cc.variable_names)

        def mutate_cluster_class_extra_var(resource):
            resource["metadata"]["name"] += "-extra-var"
            resource["spec"]["variables"].append(
                {
                    "name": "extraTestVariable",
                    "required": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "string",
                        },
                    },
                },
            )

        self.cluster_class_extra_var = self.useFixture(
            mcapi_fixtures.ClusterClassFixture(
                self.api, self.namespace, mutate_callback=mutate_cluster_class_extra_var
            )
        ).cluster_class

        cc = objects.ClusterClass.objects(
            self.pykube_api, namespace=self.namespace.name
        ).get(
            name=self.cluster_class_extra_var.get_resource().get("metadata").get("name")
        )

        self.assertIn("extraTestVariable", cc.variable_names)
        self.assertIn(
            {
                "name": "extraTestVariable",
                "metadata": {},
                "required": True,
                "schema": {
                    "openAPIV3Schema": {
                        "type": "string",
                    },
                },
            },
            cc.obj["spec"]["variables"],
        )

        self.cluster = magnum_objects.Cluster(
            self.context,
            **utils.get_test_cluster(
                master_flavor_id="m1.medium",
                flavor_id="m1.large",
                keypair="fake-keypair",
                labels={},
            ),
        )
        self.cluster.cluster_template = magnum_objects.ClusterTemplate(
            self.context,
            **utils.get_test_cluster_template(),
        )

    def _get_cluster_object(self, mutate_callback=None):
        fixture = self.useFixture(
            mcapi_fixtures.ClusterFixture(
                self.context,
                self.api,
                self.pykube_api,
                self.namespace,
                self.cluster,
                mutate_callback=mutate_callback,
            )
        )

        capi_cluster = fixture.cluster
        return objects.Cluster.objects(
            self.pykube_api, namespace=self.namespace.name
        ).get(name=capi_cluster.get_resource().get("metadata").get("name"))

    def test_cluster_variable_addition(self):
        c = self._get_cluster_object()

        self.assertEqual(
            self.cluster_class_original.get_resource().get("metadata").get("name"),
            c.obj["spec"]["topology"]["class"],
        )
        self.assertNotIn(
            {"name": "extraTestVariable", "value": "test"},
            c.obj["spec"]["topology"]["variables"],
        )

        def mutate_cluster(resource):
            resource["spec"]["topology"]["class"] = (
                self.cluster_class_extra_var.get_resource().get("metadata").get("name")
            )
            resource["spec"]["topology"]["variables"].append(
                {
                    "name": "extraTestVariable",
                    "value": "test",
                },
            )

        c = self._get_cluster_object(mutate_cluster)

        self.assertEqual(
            self.cluster_class_extra_var.get_resource().get("metadata").get("name"),
            c.obj["spec"]["topology"]["class"],
        )
        self.assertIn(
            {"name": "extraTestVariable", "value": "test"},
            c.obj["spec"]["topology"]["variables"],
        )

    def test_cluster_variable_removal(self):
        def mutate_cluster(resource):
            resource["spec"]["topology"]["class"] = (
                self.cluster_class_extra_var.get_resource().get("metadata").get("name")
            )
            resource["spec"]["topology"]["variables"].append(
                {
                    "name": "extraTestVariable",
                    "value": "test",
                },
            )

        c = self._get_cluster_object(mutate_cluster)

        self.assertEqual(
            self.cluster_class_extra_var.get_resource().get("metadata").get("name"),
            c.obj["spec"]["topology"]["class"],
        )
        self.assertIn(
            {"name": "extraTestVariable", "value": "test"},
            c.obj["spec"]["topology"]["variables"],
        )

        c = self._get_cluster_object()

        self.assertEqual(
            self.cluster_class_original.get_resource().get("metadata").get("name"),
            c.obj["spec"]["topology"]["class"],
        )
        self.assertNotIn(
            {"name": "extraTestVariable", "value": "test"},
            c.obj["spec"]["topology"]["variables"],
        )
