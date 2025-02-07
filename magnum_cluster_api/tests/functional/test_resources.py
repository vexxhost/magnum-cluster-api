# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

import string
from unittest import mock

import shortuuid
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import context as magnum_context  # type: ignore
from magnum.tests.unit.db import utils  # type: ignore
from oslo_utils import uuidutils  # type: ignore
from oslotest import base  # type: ignore
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_fixed

from magnum_cluster_api import clients, exceptions, resources


class TestClusterClass(base.BaseTestCase):
    def setUp(self):
        super(TestClusterClass, self).setUp()

        self.api = clients.get_pykube_api()

        alphabet = string.ascii_lowercase + string.digits
        su = shortuuid.ShortUUID(alphabet=alphabet)
        name = "test-%s" % (su.random(length=5))

        self.namespace = resources.Namespace(self.api, name)
        self.namespace.apply()
        self.addCleanup(self.namespace.delete)

        resources.create_cluster_class(self.api, namespace=self.namespace.name)

    @mock.patch(
        "magnum_cluster_api.clients.get_openstack_api",
    )
    @mock.patch("magnum.objects.nodegroup.NodeGroup.list")
    @mock.patch(
        "magnum_cluster_api.utils.generate_cloud_controller_manager_config",
        return_value="fake-config",
    )
    @mock.patch(
        "magnum_cluster_api.utils.get_image_uuid",
        return_value=uuidutils.generate_uuid(),
    )
    @mock.patch(
        "magnum_cluster_api.utils.ensure_controlplane_server_group",
        return_value=uuidutils.generate_uuid(),
    )
    def _test_disable_api_server_floating_ip(
        self,
        mock_ensure_controlplane_server_group,
        mock_get_image_uuid,
        mock_generate_config,
        mock_list,
        mock_get_openstack_api,
        **kwargs,
    ):
        master_lb_floating_ip_enabled = kwargs.get("master_lb_floating_ip_enabled")
        expected = kwargs.get("expected")

        mock_get_openstack_api.return_value.cinder.return_value.volume_types.default.return_value.name = (
            "fake-boot-volume-type"
        )

        context = magnum_context.RequestContext(is_admin=False)
        cluster = magnum_objects.Cluster(
            context,
            **utils.get_test_cluster(
                master_count=1,
                master_flavor_id="m1.medium",
                flavor_id="m1.large",
                keypair="fake-keypair",
                labels={},
            ),
        )
        cluster.cluster_template = magnum_objects.ClusterTemplate(
            context,
            **utils.get_test_cluster_template(),
        )

        if master_lb_floating_ip_enabled is not None:
            cluster.labels["master_lb_floating_ip_enabled"] = str(
                master_lb_floating_ip_enabled
            )

        capi_cluster = resources.Cluster(
            context, self.api, cluster, namespace=self.namespace.name
        )

        capi_cluster_obj = capi_cluster.get_object()
        for variable in capi_cluster_obj.obj["spec"]["topology"]["variables"]:
            if variable["name"] == "master_lb_floating_ip_enabled":
                self.assertEqual(expected, variable["value"])

        capi_cluster.apply()
        self.addCleanup(capi_cluster.delete)

        @retry(
            stop=stop_after_delay(10),
            wait=wait_fixed(1),
            retry=retry_if_exception_type(exceptions.OpenStackClusterNotCreated),
        )
        def get_capi_oc():
            return capi_cluster_obj.openstack_cluster

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
