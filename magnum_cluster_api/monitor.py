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

from magnum.conductor import monitors  # type: ignore
from oslo_log import log as logging  # type: ignore

from magnum_cluster_api import clients, objects, utils
from magnum_cluster_api.magnum_cluster_api import Monitor as RustMonitor

LOG = logging.getLogger(__name__)


class Monitor(monitors.MonitorBase):
    def metrics_spec(self):
        pass

    def pull_data(self):
        pass

    def poll_nodegroup_replicas(self):
        """
        Poll the number of replicas of each nodegroup in the cluster when autoscaling enabled.
        """
        k8s_api = clients.get_pykube_api()
        if not utils.get_auto_scaling_enabled(self.cluster):
            return
        for node_group in self.cluster.nodegroups:
            md = objects.MachineDeployment.for_node_group_or_none(
                k8s_api, self.cluster, node_group
            )
            if md is None:
                continue
            node_group.node_count = md.obj["spec"]["replicas"]
            node_group.save()

    def poll_health_status(self):
        rust_monitor = RustMonitor(self.cluster)
        self.data = rust_monitor.poll_health_status()

        self.poll_nodegroup_replicas()
