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

import base64
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import jinja2
import pykube
import yaml
from oslo_log import log as logging
from oslo_service import periodic_task

import magnum_cluster_api.privsep.haproxy
from magnum_cluster_api import clients, conf, objects
from magnum_cluster_api.proxy import structs, utils

CONF = conf.CONF
LOG = logging.getLogger(__name__)


class ProxyManager(periodic_task.PeriodicTasks):
    def __init__(self):
        super(ProxyManager, self).__init__(CONF)

        self.api = clients.get_pykube_api()
        self.checksum = None
        self.template = jinja2.Environment(
            loader=jinja2.PackageLoader("magnum_cluster_api.proxy"),
            autoescape=jinja2.select_autoescape(),
        ).get_template("haproxy.cfg.j2")
        self.haproxy_port = utils.find_free_port(
            port_hint=int(os.getenv("PROXY_PORT", 0))
        )
        self.haproxy_bind = os.getenv("PROXY_BIND", "*")
        self.haproxy_pid = None

    def periodic_tasks(self, context, raise_on_error=False):
        return self.run_periodic_tasks(context, raise_on_error=raise_on_error)

    def _sync_haproxy(self, proxied_clusters: list):
        # Generate HAproxy config
        config = self.template.render(
            pid_file=CONF.proxy.haproxy_pid_path,
            port=self.haproxy_port,
            bind=self.haproxy_bind,
            clusters=proxied_clusters,
        )

        # Skip if no change has been done
        if self.checksum == hash(config):
            return

        LOG.info("Detected configuration change, reloading HAproxy")

        cfg_file = Path.home() / ".magnum-cluster-api-proxy" / "haproxy.cfg"
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(config)

        if self.haproxy_pid is None:
            self.haproxy_pid = magnum_cluster_api.privsep.haproxy.start(str(cfg_file))
        else:
            magnum_cluster_api.privsep.haproxy.reload()

        # Update checksum
        self.checksum = hash(config)

    def _sync_services(self, proxied_clusters: list, openstack_clusters: list):
        labels = {
            structs.ProxiedCluster.SERVICE_LABEL: "true",
        }

        # Get all services
        services = pykube.Service.objects(self.api, namespace="magnum-system").filter(
            selector=labels
        )

        # Generate list of all cluster names
        cluster_names = [
            cluster.metadata["labels"]["cluster.x-k8s.io/cluster-name"]
            for cluster in openstack_clusters
        ]

        # Remove any services that are not supposed to be there
        for service in services:
            if service.name not in cluster_names:
                LOG.info(
                    "Deleting service %s since the cluster does not exist",
                    service.name,
                )
                service.delete()

        # Create a list of ports to expose
        ports = [
            {
                "name": "https",
                "port": 6443,
                "targetPort": 6443,
                "protocol": "TCP",
            },
        ]

        # Create any services that are missing
        for cluster in proxied_clusters:
            service_name = cluster.name

            try:
                service = pykube.Service.objects(
                    self.api, namespace="magnum-system"
                ).get(name=service_name)
            except pykube.exceptions.ObjectDoesNotExist:
                LOG.info(
                    "Creating service %s",
                    service_name,
                )
                pykube.objects.Service(
                    self.api,
                    {
                        "apiVersion": pykube.Service.version,
                        "kind": pykube.Service.kind,
                        "metadata": {
                            "name": service_name,
                            "namespace": "magnum-system",
                            "labels": labels,
                        },
                        "spec": {
                            "ports": ports,
                        },
                    },
                ).create()
                service = pykube.Service.objects(
                    self.api, namespace="magnum-system"
                ).get(name=service_name)

            if (
                service.metadata["labels"] != labels
                or service.obj["spec"]["ports"] != ports
            ):
                LOG.info("Updating service %s", service.name)
                service.metadata["labels"] = labels
                service.obj["spec"]["ports"] = ports
                service.update()

    def _sync_endpoint_slices(self, proxied_clusters: list):
        hostname = socket.gethostname()

        # Get list of all endpoint slices assigned to this host
        endpoint_slices_for_host = objects.EndpointSlice.objects(
            self.api, namespace="magnum-system"
        ).filter(selector={structs.ProxiedCluster.NODE_LABEL: hostname})

        # Get list of all endpoint slices that are supposed to exist
        proxied_clusters_endpoint_slice_names = [
            cluster.endpoint_slice_name for cluster in proxied_clusters
        ]

        # Delete EndpointSlices that are no longer needed or if they are not healthy
        for endpoint_slice in endpoint_slices_for_host:
            if endpoint_slice.name not in proxied_clusters_endpoint_slice_names:
                LOG.info(
                    "Deleting EndpointSlice %s since it is not proxied on this host",
                    endpoint_slice.name,
                )
                endpoint_slice.delete()
                continue

            proxied_cluster = structs.ProxiedCluster.from_endpoint_slice(endpoint_slice)
            if not proxied_cluster.healthy:
                LOG.info(
                    "Deleting unhealthy EndpointSlice %s since the backend is unhealthy",
                    endpoint_slice.name,
                )
                endpoint_slice.delete()
                continue

        # Create EndpointSlices for each cluster
        for proxied_cluster in proxied_clusters:
            # Skip creating endpoint slices if the backend is unhealthy
            if not proxied_cluster.healthy:
                continue

            endpoint_slice_ports = proxied_cluster.endpoint_slice_ports(
                haproxy_port=self.haproxy_port
            )

            try:
                endpoint_slice = objects.EndpointSlice.objects(
                    self.api, namespace="magnum-system"
                ).get(name=proxied_cluster.endpoint_slice_name)
            except pykube.exceptions.ObjectDoesNotExist:
                LOG.info(
                    "Creating EndpointSlice %s", proxied_cluster.endpoint_slice_name
                )
                objects.EndpointSlice(
                    self.api,
                    {
                        "apiVersion": objects.EndpointSlice.version,
                        "kind": objects.EndpointSlice.kind,
                        "metadata": {
                            "name": proxied_cluster.endpoint_slice_name,
                            "namespace": "magnum-system",
                            "labels": proxied_cluster.endpoint_slice_labels,
                            "annotations": proxied_cluster.endpoint_slice_annotations,
                        },
                        "addressType": "IPv4",
                        "endpoints": proxied_cluster.endpoint_slice_endpoints,
                        "ports": endpoint_slice_ports,
                    },
                ).create()
                endpoint_slice = objects.EndpointSlice.objects(
                    self.api, namespace="magnum-system"
                ).get(name=proxied_cluster.endpoint_slice_name)

            # NOTE(mnaser): We always update the annotations since it contains the timestamp
            #               which we need for liveness.
            endpoint_slice.metadata["annotations"] = (
                proxied_cluster.endpoint_slice_annotations
            )
            endpoint_slice.update()

            if (
                endpoint_slice.metadata["labels"]
                != proxied_cluster.endpoint_slice_labels
                or endpoint_slice.obj["endpoints"]
                != proxied_cluster.endpoint_slice_endpoints
                or endpoint_slice.obj["ports"] != endpoint_slice_ports
            ):
                if (
                    endpoint_slice.metadata["labels"]
                    != proxied_cluster.endpoint_slice_labels
                ):
                    LOG.info(
                        "old_labels: %s, new_labels: %s",
                        endpoint_slice.labels,
                        proxied_cluster.endpoint_slice_labels,
                    )
                    endpoint_slice.metadata["labels"] = (
                        proxied_cluster.endpoint_slice_labels
                    )

                if (
                    endpoint_slice.obj["endpoints"]
                    != proxied_cluster.endpoint_slice_endpoints
                ):
                    LOG.info(
                        "old_endpoints: %s, new_endpoints: %s",
                        endpoint_slice.obj["endpoints"],
                        proxied_cluster.endpoint_slice_endpoints,
                    )
                    endpoint_slice.obj["endpoints"] = (
                        proxied_cluster.endpoint_slice_endpoints
                    )

                if endpoint_slice.obj["ports"] != endpoint_slice_ports:
                    LOG.info(
                        "old_ports: %s, new_ports: %s",
                        endpoint_slice.obj["ports"],
                        endpoint_slice_ports,
                    )
                    endpoint_slice.obj["ports"] = endpoint_slice_ports

                LOG.info("Updating EndpointSlice %s", endpoint_slice.name)
                endpoint_slice.update()

    def _sync_kubeconfigs(self, proxied_clusters: list):
        for cluster in proxied_clusters:
            # NOTE(mnaser): We only modify the `kubeconfig` if the cluster does
            #               not have a floating IP enabled.
            endpoint = f"https://{cluster.name}.magnum-system:6443"

            # Get the kubeconfig secret
            try:
                secret = pykube.Secret.objects(self.api, namespace="magnum-system").get(
                    name=cluster.kubeconfig_secret_name
                )
            except pykube.exceptions.ObjectDoesNotExist:
                LOG.warning(
                    "Kubeconfig secret %s does not exist",
                    cluster.kubeconfig_secret_name,
                )
                return

            # Get the kubeconfig from the secret
            kubeconfig = base64.b64decode(secret.obj["data"]["value"]).decode("utf-8")
            kubeconfig = yaml.safe_load(kubeconfig)

            # Check if the kubeconfig needs to be updated
            if kubeconfig["clusters"][0]["cluster"]["server"] == endpoint:
                continue

            # Update the kubeconfig endpoint
            LOG.info("Updating kubeconfig %s", cluster.kubeconfig_secret_name)
            kubeconfig["clusters"][0]["cluster"]["server"] = endpoint

            # Update the secret with the new kubeconfig
            secret.obj["data"]["value"] = base64.b64encode(
                yaml.safe_dump(kubeconfig).encode("utf-8")
            ).decode("utf-8")
            secret.update()

    def _cleanup_endpoint_slices(self):
        # Get list of all endpoint slices managed by the proxy service
        endpoint_slices = objects.EndpointSlice.objects(
            self.api, namespace="magnum-system"
        ).filter(selector={structs.ProxiedCluster.SERVICE_LABEL: "true"})

        # Look if any of the endpoint slices should be expired (aka >30s age)
        for endpoint_slice in endpoint_slices:
            timestamp = datetime.fromisoformat(
                endpoint_slice.metadata["annotations"][
                    structs.ProxiedCluster.TIMESTAMP_ANNOTATION
                ]
            )

            if (datetime.now(timezone.utc) - timestamp).total_seconds() > 30:
                LOG.info("Deleting expired EndpointSlice %s", endpoint_slice.name)
                endpoint_slice.delete()

    @periodic_task.periodic_task(spacing=10, run_immediately=True)
    def sync(self, context):
        # Generate list of all clusters
        clusters = objects.OpenStackCluster.objects(
            self.api, namespace="magnum-system"
        ).all()

        # Generate list of proxied clusters
        proxied_clusters = []
        for cluster in clusters:
            proxied_cluster = structs.ProxiedCluster.from_openstack_cluster(cluster)
            if proxied_cluster:
                proxied_clusters.append(proxied_cluster)

        self._sync_haproxy(proxied_clusters)
        self._sync_services(proxied_clusters, clusters)
        self._sync_endpoint_slices(proxied_clusters)
        self._sync_kubeconfigs(proxied_clusters)
        self._cleanup_endpoint_slices()
