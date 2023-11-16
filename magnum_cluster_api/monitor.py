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

from magnum.conductor import monitors
from magnum.objects import fields
from oslo_log import log as logging
from oslo_utils import strutils

from magnum_cluster_api import clients, objects, resources, utils

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
            md = resources.get_machine_deployment(k8s_api, self.cluster, node_group)
            if md is None:
                continue
            node_group.node_count = md.obj["spec"]["replicas"]
            node_group.save()

    def poll_health_status(self):
        k8s_api = clients.get_pykube_api()
        self.data = {
            "health_status": fields.ClusterHealthStatus.UNKNOWN,
            "health_status_reason": {},
        }

        machines = objects.Machine.objects(k8s_api).filter(
            namespace="magnum-system",
            selector={
                "cluster.x-k8s.io/cluster-name": self.cluster.stack_id,
            },
        )

        if len(machines) == 0:
            return

        for machine in machines:
            condition_map = {
                c["type"]: c["status"] for c in machine.obj["status"]["conditions"]
            }

            node_healthy = condition_map.get("NodeHealthy", False)
            health_status = strutils.bool_from_string(node_healthy)
            self.data["health_status_reason"][f"{machine.name}.Ready"] = health_status

            if health_status is False:
                self.data["health_status"] = fields.ClusterHealthStatus.UNHEALTHY

        if self.data["health_status"] == fields.ClusterHealthStatus.UNKNOWN:
            self.data["health_status"] = fields.ClusterHealthStatus.HEALTHY

        self.poll_nodegroup_replicas()
