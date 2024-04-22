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
            if "certificatesExpiryDays" not in rollout_before:
                kcpt.obj["spec"]["template"]["spec"].setdefault("rolloutBefore", {})
                kcpt.obj["spec"]["template"]["spec"]["rolloutBefore"][
                    "certificatesExpiryDays"
                ] = 21

                # NOTE(mnaser): Since the KubeadmControlPlaneTemplate is immutable, we need to
                #               delete the object and re-create it.
                kcpt.delete()
                del kcpt.obj["metadata"]["uid"]

                utils.kube_apply_patch(kcpt)

        CERTIFICATE_EXPIRY_DAYS_FIX_APPLIED = True
