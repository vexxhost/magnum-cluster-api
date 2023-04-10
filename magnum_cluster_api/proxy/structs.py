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

import dataclasses
import os
import socket

from oslo_log import log as logging
from pyroute2 import netns

from magnum_cluster_api import objects
from magnum_cluster_api.proxy import utils

LOG = logging.getLogger(__name__)


@dataclasses.dataclass
class ProxiedCluster:
    """A cluster that is proxied by this service."""

    NODE_LABEL = "magnum-cluster-api.vexxhost.com/node"
    CLUSTER_LABEL = "magnum-cluster-api.vexxhost.com/proxied-cluster"
    SERVICE_LABEL = "magnum-cluster-api.vexxhost.com/proxied-service"

    name: str
    internal_ip: str
    namespace: str

    @classmethod
    def from_openstack_cluster(
        self, cluster: objects.OpenStackCluster
    ) -> "ProxiedCluster":
        spec = cluster.obj.get("spec", {})

        # NOTE(mnaser): If the API server floating IP is disabled, we don't
        #               need to proxy it.
        if spec.get("disableAPIServerFloatingIP", False) is False:
            return None

        status = cluster.obj.get("status", {})
        network = status.get("network", {})

        internal_ip = network.get("apiServerLoadBalancer", {}).get("internalIP")
        network_id = network.get("id")

        if network_id is None:
            LOG.debug("No network ID found for cluster %s", cluster.name)
            return

        namespaces = [n for n in netns.listnetns() if n.endswith(network_id)]
        if len(namespaces) == 0:
            LOG.debug("No namespaces found for network %s", network_id)
            return

        return ProxiedCluster(
            name=cluster.metadata["labels"]["cluster.x-k8s.io/cluster-name"],
            internal_ip=internal_ip,
            namespace=namespaces[0],
        )

    @property
    def endpoint_slice_name(self) -> str:
        return f"{self.name}-{socket.gethostname()}"

    @property
    def endpoint_slice_labels(self) -> dict:
        return {
            "kubernetes.io/service-name": self.name,
            self.NODE_LABEL: socket.gethostname(),
            self.CLUSTER_LABEL: self.name,
        }

    @property
    def endpoint_slice_endpoints(self) -> list:
        ip = os.getenv("POD_IP", utils.get_default_ip_address())

        return [
            {
                "addresses": [ip],
                "conditions": {
                    "ready": True,
                },
                "nodeName": socket.gethostname(),
            }
        ]

    def endpoint_slice_ports(self, haproxy_port) -> list:
        return [
            {
                "name": "https",
                "port": haproxy_port,
                "protocol": "TCP",
            }
        ]

    @property
    def kubeconfig_secret_name(self) -> str:
        return f"{self.name}-kubeconfig"
