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

import configparser
import copy
import io

import pykube
import yaml
from magnum import objects as magnum_objects
from oslo_serialization import base64
from tenacity import Retrying, retry_if_result, stop_after_delay, wait_fixed

from magnum_cluster_api import exceptions


class NamespacedAPIObject(pykube.objects.NamespacedAPIObject):
    @property
    def events(self):
        return pykube.Event.objects(self.api, namespace=self.namespace).filter(
            field_selector={
                "involvedObject.name": self.name,
                "involvedObject.apiVersion": self.version,
                "involvedObject.kind": self.kind,
            },
        )

    @property
    def observed_generation(self):
        return self.obj.get("status", {}).get("observedGeneration")

    def wait_for_observed_generation_changed(
        self,
        existing_observed_generation: int = 0,
        timeout: int = 10,
        interval: int = 1,
    ):
        if existing_observed_generation == 0:
            existing_observed_generation = self.observed_generation

        for attempt in Retrying(
            retry=(
                retry_if_result(lambda g: g == existing_observed_generation)
                | retry_if_result(lambda g: g is None)
            ),
            stop=stop_after_delay(timeout),
            wait=wait_fixed(interval),
        ):
            with attempt:
                self.reload()
            if not attempt.retry_state.outcome.failed:
                attempt.retry_state.set_result(self.observed_generation)


class EndpointSlice(NamespacedAPIObject):
    version = "discovery.k8s.io/v1"
    endpoint = "endpointslices"
    kind = "EndpointSlice"


class ClusterResourceSet(NamespacedAPIObject):
    version = "addons.cluster.x-k8s.io/v1beta1"
    endpoint = "clusterresourcesets"
    kind = "ClusterResourceSet"


class OpenStackMachineTemplate(NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1beta1"
    endpoint = "openstackmachinetemplates"
    kind = "OpenStackMachineTemplate"


class KubeadmConfigTemplate(NamespacedAPIObject):
    version = "bootstrap.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmconfigtemplates"
    kind = "KubeadmConfigTemplate"


class KubeadmControlPlane(NamespacedAPIObject):
    version = "controlplane.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmcontrolplanes"
    kind = "KubeadmControlPlane"


class KubeadmControlPlaneTemplate(NamespacedAPIObject):
    version = "controlplane.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmcontrolplanetemplates"
    kind = "KubeadmControlPlaneTemplate"


class MachineDeployment(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machinedeployments"
    kind = "MachineDeployment"

    @classmethod
    def for_node_group(
        cls,
        api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
        node_group: magnum_objects.NodeGroup,
    ):
        mds = cls.objects(api, namespace="magnum-system").filter(
            selector={
                "cluster.x-k8s.io/cluster-name": cluster.stack_id,
                "topology.cluster.x-k8s.io/deployment-name": node_group.name,
            },
        )
        if len(mds) != 1:
            raise exceptions.MachineDeploymentNotFound(name=node_group.name)
        return list(mds)[0]

    @classmethod
    def for_node_group_or_none(
        cls,
        api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
        node_group: magnum_objects.NodeGroup,
    ):
        try:
            return cls.for_node_group(api, cluster, node_group)
        except exceptions.MachineDeploymentNotFound:
            return None

    def equals_spec(self, spec: dict) -> bool:
        expected_annotations = spec["metadata"].get("annotations")
        current_annotations = self.obj["spec"]["template"]["metadata"].get(
            "annotations"
        )

        # NOTE(mnaser): If we have any annotations, that means that autoscaling is
        #               enabled and we should not compare the replicas.
        if expected_annotations:
            return expected_annotations == current_annotations

        expected_replicas = spec.get("replicas")
        current_replicas = self.obj["spec"].get("replicas")

        return expected_replicas == current_replicas


class Machine(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machines"
    kind = "Machine"


class OpenStackClusterTemplate(NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1beta1"
    endpoint = "openstackclustertemplates"
    kind = "OpenStackClusterTemplate"


class OpenStackCluster(NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1beta1"
    endpoint = "openstackclusters"
    kind = "OpenStackCluster"

    @property
    def identity_ref(self):
        return self.obj["spec"]["identityRef"]

    @property
    def identity_ref_secret(self) -> pykube.Secret:
        return pykube.Secret.objects(self.api, namespace=self.namespace).get(
            name=self.identity_ref["name"]
        )

    @property
    def clouds_yaml(self):
        return yaml.safe_load(
            base64.decode_as_text(self.identity_ref_secret.obj["data"]["clouds.yaml"])
        )

    @property
    def cloud_config(self):
        return self.clouds_yaml["clouds"]["default"]

    @property
    def floating_network_id(self):
        try:
            return self.obj["status"]["externalNetwork"]["id"]
        except KeyError:
            raise exceptions.OpenStackClusterExternalNetworkNotReady()

    @property
    def network_id(self):
        try:
            return self.obj["status"]["network"]["id"]
        except KeyError:
            raise exceptions.OpenStackClusterNetworkNotReady()

    @property
    def subnet_id(self):
        try:
            return self.obj["status"]["network"]["subnet"]["id"]
        except KeyError:
            raise exceptions.OpenStackClusterSubnetNotReady()

    @property
    def cloud_controller_manager_config(self):
        config = configparser.ConfigParser()
        config["Global"] = {
            "auth-url": self.cloud_config["auth"]["auth_url"],
            "region": self.cloud_config["region_name"],
            "application-credential-id": self.cloud_config["auth"][
                "application_credential_id"
            ],
            "application-credential-secret": self.cloud_config["auth"][
                "application_credential_secret"
            ],
            "tls-insecure": "false" if self.cloud_config["verify"] else "true",
        }
        config["LoadBalancer"] = {
            "floating-network-id": self.floating_network_id,
            "network-id": self.network_id,
            "subnet-id": self.subnet_id,
        }

        fd = io.StringIO()
        config.write(fd)

        return fd.getvalue()


class ClusterClass(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusterclasses"
    kind = "ClusterClass"


class Cluster(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusters"
    kind = "Cluster"

    @classmethod
    def for_magnum_cluster(
        cls, api: pykube.HTTPClient, cluster: magnum_objects.Cluster
    ) -> "Cluster":
        return cls.objects(api, namespace="magnum-system").get(name=cluster.stack_id)

    @classmethod
    def for_magnum_cluster_or_none(
        cls, api: pykube.HTTPClient, cluster: magnum_objects.Cluster
    ) -> "Cluster":
        return cls.objects(api, namespace="magnum-system").get_or_none(
            name=cluster.stack_id
        )

    def get_machine_deployment_index(self, name: str) -> int:
        for i, machine_deployment in enumerate(
            self.obj["spec"]["topology"]["workers"]["machineDeployments"]
        ):
            if machine_deployment["name"] == name:
                return i

        raise exceptions.MachineDeploymentNotFound(name=name)

    def get_machine_deployment_spec(self, name: str) -> dict:
        return copy.deepcopy(
            self.obj["spec"]["topology"]["workers"]["machineDeployments"][
                self.get_machine_deployment_index(name)
            ]
        )

    def set_machine_deployment_spec(self, name: str, spec: dict):
        self.obj["spec"]["topology"]["workers"]["machineDeployments"][
            self.get_machine_deployment_index(name)
        ] = spec

    @property
    def openstack_cluster(self):
        filtered_clusters = (
            OpenStackCluster.objects(self.api, namespace=self.namespace)
            .filter(selector={"cluster.x-k8s.io/cluster-name": self.name})
            .all()
        )

        if len(filtered_clusters) == 0:
            raise exceptions.OpenStackClusterNotCreated()

        return list(filtered_clusters)[0]


class OpenStackMachine(NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1beta1"
    endpoint = "openstackmachines"
    kind = "OpenStackMachine"


class StorageClass(pykube.objects.APIObject):
    version = "storage.k8s.io/v1"
    endpoint = "storageclasses"
    kind = "StorageClass"
