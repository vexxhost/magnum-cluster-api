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

from magnum.conductor import k8s_api as k8s
from magnum.drivers.common import k8s_monitor
from oslo_log import log as logging

from magnum_cluster_api import utils

LOG = logging.getLogger(__name__)


class Monitor(k8s_monitor.K8sMonitor):
    def poll_health_status(self):
        # NOTE(mnaser): We override the `api_address` for the cluster if it's
        #               an isolated cluster so we can go through the proxy.
        if utils.get_cluster_floating_ip_disabled(self.cluster):
            api_address = f"https://{self.cluster.stack_id}.magnum-system:6443"
            self.cluster.api_address = api_address
            LOG.debug("Overriding cluster api_address to %s", api_address)

        k8s_api = k8s.KubernetesAPI(self.context, self.cluster)
        status, reason = self._poll_health_status(k8s_api)

        self.data["health_status"] = status
        self.data["health_status_reason"] = reason
