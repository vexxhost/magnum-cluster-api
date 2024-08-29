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
from datetime import datetime, timezone

import haproxyadmin
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
    TIMESTAMP_ANNOTATION = "magnum-cluster-api.vexxhost.com/timestamp"

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
        if (
            os.getenv("PROXY_ALWAYS", 0) == 0
            and spec.get("disableAPIServerFloatingIP", False) is False
        ):
            return None

        status = cluster.obj.get("status", {})

        network_id = status.get("network", {}).get("id")
        if network_id is None:
            LOG.debug("No network ID found for cluster %s", cluster.name)
            return

        internal_ip = status.get("apiServerLoadBalancer", {}).get("internalIP")
        if internal_ip is None:
            LOG.debug("No internal IP found for cluster %s", cluster.name)
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

    @classmethod
    def from_endpoint_slice(
        cls, endpoint_slice: objects.EndpointSlice
    ) -> "ProxiedCluster":
        """
        Returns a ProxiedCluster object from an endpoint slice.

        This is used when we're looking up a cluster from an endpoint slice
        and we need to get the cluster name from the endpoint slice.
        """
        return ProxiedCluster(
            name=endpoint_slice.metadata["labels"][cls.CLUSTER_LABEL],
            namespace=endpoint_slice.namespace,
            # TODO(mnaser): We can try and figure out a way to get this, but
            #               when we're looking up from the endpoint slice, we
            #               don't really need it.
            internal_ip="",
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
            self.SERVICE_LABEL: "true",
        }

    @property
    def endpoint_slice_annotations(self) -> dict:
        return {
            self.TIMESTAMP_ANNOTATION: datetime.now(timezone.utc).isoformat(),
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

    @property
    def backend_name(self) -> str:
        """
        Returns the name of the backend for this cluster.
        """
        return f"{self.name}.magnum-system"

    @property
    def backend(self) -> haproxyadmin.backend.Backend:
        """
        Returns the backend object for this cluster.
        """
        hap = haproxyadmin.haproxy.HAProxy(socket_dir="/var/run")
        return hap.backend(self.backend_name)

    @property
    def healthy(self) -> bool:
        """
        Returns whether the backend is healthy or not.
        """
        try:
            return self.backend.status == "UP"
        except ValueError:
            LOG.error("Backend %s does not exist", self.backend_name)
            return False
