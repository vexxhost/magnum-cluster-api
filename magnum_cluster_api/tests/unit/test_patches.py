# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

from oslotest import base

from magnum_cluster_api import objects, patches


class TestDisableApiServerFloatingIpClusterClassPatch(base.BaseTestCase):
    """
    Test case for DisableApiServerFloatingIpClusterClassPatch.

    This isn't great, but it's something.  We should ideally be able to template out
    the `enabledIf` and make sure that given a specific label, we get a specific
    result.
    """

    def test_asdict(self):
        patch = patches.DISABLE_API_SERVER_FLOATING_IP.to_dict()

        self.assertEqual(
            {
                "name": "disableAPIServerFloatingIP",
                "enabledIf": "{{ if .disableAPIServerFloatingIP }}true{{end}}",
                "definitions": [
                    {
                        "selector": {
                            "apiVersion": objects.OpenStackClusterTemplate.version,
                            "kind": objects.OpenStackClusterTemplate.kind,
                            "matchResources": {
                                "infrastructureCluster": True,
                            },
                        },
                        "jsonPatches": [
                            {
                                "op": "add",
                                "path": "/spec/template/spec/disableAPIServerFloatingIP",
                                "valueFrom": {"variable": "disableAPIServerFloatingIP"},
                            },
                        ],
                    },
                ],
            },
            patch,
        )

    def test_enabled_if(self):
        patch = patches.DISABLE_API_SERVER_FLOATING_IP

        # https://github.com/kubernetes-sigs/cluster-api-provider-openstack/issues/2408
        self.assertEqual(
            "{{ if .disableAPIServerFloatingIP }}true{{end}}", patch.enabledIf
        )
