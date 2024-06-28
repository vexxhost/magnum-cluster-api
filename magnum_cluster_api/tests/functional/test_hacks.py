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
from tenacity import Retrying, retry_if_result, stop_after_delay, wait_fixed

from magnum_cluster_api import clients, hacks, objects, resources, utils


@pytest.fixture
def kubeadm_control_plane_template_without_certificates_expiry_days():
    api = clients.get_pykube_api()

    kcpf = resources.KubeadmControlPlaneTemplate(api).get_object()
    kcpf.obj["metadata"]["name"] = "test-hacks-set-certificate-expiry-days"

    rollout_before = kcpf.obj["spec"]["template"]["spec"].pop("rolloutBefore", {})
    assert "certificatesExpiryDays" in rollout_before

    utils.kube_apply_patch(kcpf)
    yield kcpf
    kcpf.delete()


@pytest.fixture
def cluster_class_without_certificates_expiry_days(
    kubeadm_control_plane_template_without_certificates_expiry_days,
):
    api = clients.get_pykube_api()

    cc = resources.ClusterClass(api).get_object()
    cc.obj["metadata"]["name"] = "test-hacks-set-certificate-expiry-days"
    cc.obj["spec"]["controlPlane"]["ref"][
        "name"
    ] = kubeadm_control_plane_template_without_certificates_expiry_days.name

    utils.kube_apply_patch(cc)
    yield cc
    cc.delete()


class TestHacks:
    @pytest.fixture(autouse=True)
    def setup(self, cluster):
        self.api = clients.get_pykube_api()
        self.cluster = cluster

    def test_set_certificate_expiry_days(
        self, context, cluster_class_without_certificates_expiry_days
    ):
        # Delete the created Cluster resource
        resources.Cluster(context, self.api, self.cluster).delete()

        # Use tenacity to wait for cluster to be deleted
        for attempt in Retrying(
            retry=retry_if_result(lambda result: result is not None),
            stop=stop_after_delay(10),
            wait=wait_fixed(1),
        ):
            with attempt:
                capi_cluster = resources.Cluster(
                    context, self.api, self.cluster
                ).get_or_none()
            if not attempt.retry_state.outcome.failed:
                attempt.retry_state.set_result(capi_cluster)

        try:
            # Create a new Cluster resource with the updated ClusterClass
            resources.Cluster(
                context,
                self.api,
                self.cluster,
                cluster_class_without_certificates_expiry_days.name,
            ).apply()

            # Wait for the Cluster to be ready
            cluster_resource = objects.Cluster.for_magnum_cluster(
                self.api, self.cluster
            )
            cluster_resource.wait_for_observed_generation_changed(
                existing_observed_generation=1
            )

            # Get the current KCP
            kcp = resources.get_kubeadm_control_plane(self.api, self.cluster)

            # Run the hack
            hacks.set_certificate_expiry_days(self.api)

            # Check if the KCPTemplate has been updated
            kcp_template = objects.KubeadmControlPlaneTemplate.objects(
                self.api, namespace="magnum-system"
            ).get(
                name=cluster_class_without_certificates_expiry_days.obj["spec"][
                    "controlPlane"
                ]["ref"]["name"]
            )
            assert (
                kcp_template.obj["spec"]["template"]["spec"]["rolloutBefore"][
                    "certificatesExpiryDays"
                ]
                == 21
            )

            # Wait for the KubeadmControlPlane to reconcile
            kcp.wait_for_observed_generation_changed()

            # Assert that the hack has been applied
            kcp = resources.get_kubeadm_control_plane(self.api, self.cluster)
            assert kcp.obj["spec"]["rolloutBefore"]["certificatesExpiryDays"] == 21
        finally:
            # Delete the created Cluster resource
            resources.Cluster(context, self.api, self.cluster).delete()

            # Use tenacity to wait for cluster to be deleted
            for attempt in Retrying(
                retry=retry_if_result(lambda result: result is not None),
                stop=stop_after_delay(10),
                wait=wait_fixed(1),
            ):
                with attempt:
                    capi_cluster = resources.Cluster(
                        context, self.api, self.cluster
                    ).get_or_none()
                if not attempt.retry_state.outcome.failed:
                    attempt.retry_state.set_result(capi_cluster)
