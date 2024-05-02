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

"""
The purpose of this module is to provide a list of hacks and workarounds
in place for modifications done to existing Cluster API resources to
address issues in pre-existing clusters without changing their entire
ClusterClass.
"""

import pykube
from tenacity import Retrying, retry_if_result, stop_after_delay, wait_fixed

from magnum_cluster_api import objects, utils

CERTIFICATE_EXPIRY_DAYS_FIX_APPLIED = False


def set_certificate_expiry_days(
    api: pykube.HTTPClient,
):
    global CERTIFICATE_EXPIRY_DAYS_FIX_APPLIED
    if not CERTIFICATE_EXPIRY_DAYS_FIX_APPLIED:
        kcpts = objects.KubeadmControlPlaneTemplate.objects(
            api, namespace="magnum-system"
        ).all()
        for kcpt in kcpts:
            rollout_before = kcpt.obj["spec"]["template"]["spec"].get(
                "rolloutBefore", {}
            )
            if "certificatesExpiryDays" in rollout_before:
                continue

            # NOTE(mnaser): Since the KubeadmControlPlaneTemplate is immutable, we need to
            #               delete the object and re-create it.
            kcpt.delete()

            del kcpt.obj["metadata"]["uid"]
            kcpt.obj["spec"]["template"]["spec"].setdefault("rolloutBefore", {})
            kcpt.obj["spec"]["template"]["spec"]["rolloutBefore"][
                "certificatesExpiryDays"
            ] = 21

            # Use tenacity to wait for kcpt to be created
            for attempt in Retrying(
                retry=retry_if_result(lambda result: result is None),
                stop=stop_after_delay(10),
                wait=wait_fixed(1),
            ):
                with attempt:
                    utils.kube_apply_patch(kcpt)
                    new_kcpt = objects.KubeadmControlPlaneTemplate.objects(
                        api, namespace="magnum-system"
                    ).get(name=kcpt.obj["metadata"]["name"])
                if not attempt.retry_state.outcome.failed:
                    attempt.retry_state.set_result(new_kcpt)

        CERTIFICATE_EXPIRY_DAYS_FIX_APPLIED = True
