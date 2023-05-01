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

import tempfile
from contextlib import contextmanager

import pykube
import yaml
from oslo_serialization import base64
from oslo_utils import strutils

from magnum_cluster_api import conf, exceptions, images

CONF = conf.CONF


class EndpointSlice(pykube.objects.NamespacedAPIObject):
    version = "discovery.k8s.io/v1"
    endpoint = "endpointslices"
    kind = "EndpointSlice"


class ClusterResourceSet(pykube.objects.NamespacedAPIObject):
    version = "addons.cluster.x-k8s.io/v1beta1"
    endpoint = "clusterresourcesets"
    kind = "ClusterResourceSet"


class OpenStackMachineTemplate(pykube.objects.NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1alpha6"
    endpoint = "openstackmachinetemplates"
    kind = "OpenStackMachineTemplate"


class KubeadmConfigTemplate(pykube.objects.NamespacedAPIObject):
    version = "bootstrap.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmconfigtemplates"
    kind = "KubeadmConfigTemplate"


class KubeadmControlPlane(pykube.objects.NamespacedAPIObject):
    version = "controlplane.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmcontrolplanes"
    kind = "KubeadmControlPlane"


class KubeadmControlPlaneTemplate(pykube.objects.NamespacedAPIObject):
    version = "controlplane.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmcontrolplanetemplates"
    kind = "KubeadmControlPlaneTemplate"


class MachineDeployment(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machinedeployments"
    kind = "MachineDeployment"


class Machine(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machines"
    kind = "Machine"


class OpenStackClusterTemplate(pykube.objects.NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1alpha6"
    endpoint = "openstackclustertemplates"
    kind = "OpenStackClusterTemplate"


class OpenStackCluster(pykube.objects.NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1alpha6"
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


class ClusterClass(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusterclasses"
    kind = "ClusterClass"


class Cluster(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusters"
    kind = "Cluster"

    @property
    def api_address(self) -> str:
        endpoint = self.obj.get("spec", {}).get("controlPlaneEndpoint")
        if endpoint is None:
            raise exceptions.ClusterEndpointNotReady()
        return f"https://{endpoint['host']}:{endpoint['port']}"

    @property
    def conditions(self) -> dict:
        return {
            c["type"]: strutils.bool_from_string(c["status"])
            for c in self.obj.get("status", {}).get("conditions", [])
        }

    @property
    def kubernetes_version(self) -> str:
        version = self.obj.get("spec", {}).get("topology", {}).get("version")
        if version is None:
            raise exceptions.ClusterVersionNotReady()
        return version

    @property
    def kubeconfig_secret_name(self) -> str:
        return f"{self.name}-kubeconfig"

    @property
    def kubeconfig(self) -> str:
        secret = pykube.Secret.objects(self.api, namespace=self.namespace).get_or_none(
            name=self.kubeconfig_secret_name
        )
        if secret is None:
            raise exceptions.ClusterKubeConfigNotReady()
        return base64.decode_as_text(secret.obj["data"]["value"])

    @contextmanager
    def config_file(self):
        with tempfile.NamedTemporaryFile() as fd:
            fd.write(self.kubeconfig.encode())
            fd.flush()
            fd.seek(0)

            yield fd

    @property
    def openstack_cluster(self):
        filtered_clusters = list(
            OpenStackCluster.objects(self.api, namespace=self.namespace)
            .filter(selector={"cluster.x-k8s.io/cluster-name": self.name})
            .all()
        )

        if len(filtered_clusters) == 0:
            raise exceptions.OpenStackClusterNotCreated()

        return filtered_clusters[0]

    @property
    def cloud_controller_manager_values(self):
        image_repository, image_tag = images.get_cloud_controller_manager_image(
            self.kubernetes_version
        ).split(":")
        cloud_config = self.openstack_cluster.cloud_config

        return {
            "image": {
                "repository": image_repository,
                "tag": image_tag,
            },
            "nodeSelector": {
                "node-role.kubernetes.io/control-plane": "",
            },
            "tolerations": [
                {
                    "key": "node-role.kubernetes.io/control-plane",
                    "effect": "NoSchedule",
                },
                {
                    "key": "node.cloudprovider.kubernetes.io/uninitialized",
                    "effect": "NoSchedule",
                    "value": "true",
                },
            ],
            "cloudConfig": {
                "global": {
                    "auth-url": cloud_config["auth"]["auth_url"],
                    "region": cloud_config["region_name"],
                    "application-credential-id": cloud_config["auth"][
                        "application_credential_id"
                    ],
                    "application-credential-secret": cloud_config["auth"][
                        "application_credential_secret"
                    ],
                    "tls-insecure": "false" if cloud_config["verify"] else "true",
                },
                "loadBalancer": {
                    "floating-network-id": self.openstack_cluster.floating_network_id,
                    "network-id": self.openstack_cluster.network_id,
                    "subnet-id": self.openstack_cluster.subnet_id,
                },
            },
            "extraVolumes": [
                {
                    "name": "ca-certs",
                    "hostPath": {
                        "path": "/etc/ssl/certs",
                    },
                },
                {
                    "name": "k8s-certs",
                    "hostPath": {
                        "path": "/etc/kubernetes/pki",
                    },
                },
            ],
            "extraVolumeMounts": [
                {
                    "name": "ca-certs",
                    "mountPath": "/etc/ssl/certs",
                    "readOnly": True,
                },
                {
                    "name": "k8s-certs",
                    "mountPath": "/etc/kubernetes/pki",
                    "readOnly": True,
                },
            ],
            "cluster": {
                "name": self.metadata["labels"]["cluster-uuid"],
            },
        }

    @property
    def cinder_csi_values(self):
        attacher_image_repository, attacher_image_tag = CONF.csi.attacher_image.split(
            ":"
        )
        (
            provisioner_image_repository,
            provisioner_image_tag,
        ) = CONF.csi.provisioner_image.split(":")
        (
            snapshotter_image_repository,
            snapshotter_image_tag,
        ) = CONF.csi.snapshotter_image.split(":")
        resizer_image_repository, resizer_image_tag = CONF.csi.resizer_image.split(":")
        (
            liveness_probe_image_repository,
            liveness_probe_image_tag,
        ) = CONF.csi.liveness_probe_image.split(":")
        (
            node_driver_registrar_image_repository,
            node_driver_registrar_image_tag,
        ) = CONF.csi.node_driver_registrar_image.split(":")
        (
            cinder_csi_plugin_image_repository,
            cinder_csi_plugin_image_tag,
        ) = images.get_cinder_csi_plugin_image(self.kubernetes_version).split(":")

        return {
            "csi": {
                "attacher": {
                    "image": {
                        "repository": attacher_image_repository,
                        "tag": attacher_image_tag,
                    }
                },
                "provisioner": {
                    "image": {
                        "repository": provisioner_image_repository,
                        "tag": provisioner_image_tag,
                    }
                },
                "snapshotter": {
                    "image": {
                        "repository": snapshotter_image_repository,
                        "tag": snapshotter_image_tag,
                    }
                },
                "resizer": {
                    "image": {
                        "repository": resizer_image_repository,
                        "tag": resizer_image_tag,
                    }
                },
                "livenessprobe": {
                    "image": {
                        "repository": liveness_probe_image_repository,
                        "tag": liveness_probe_image_tag,
                    }
                },
                "nodeDriverRegistrar": {
                    "image": {
                        "repository": node_driver_registrar_image_repository,
                        "tag": node_driver_registrar_image_tag,
                    }
                },
                "plugin": {
                    "image": {
                        "repository": cinder_csi_plugin_image_repository,
                        "tag": cinder_csi_plugin_image_tag,
                    },
                    "controllerPlugin": {
                        "nodeSelector": {
                            "node-role.kubernetes.io/control-plane": "",
                        },
                        "tolerations": [
                            {
                                "key": "node-role.kubernetes.io/control-plane",
                                "effect": "NoSchedule",
                            },
                        ],
                    },
                },
            },
            "secret": {
                "enabled": True,
                "name": "cloud-config",
            },
            "storageClass": {
                "enabled": False,
            },
            "clusterID": self.metadata["labels"]["cluster-uuid"],
        }


class StorageClass(pykube.objects.APIObject):
    version = "storage.k8s.io/v1"
    endpoint = "storageclasses"
    kind = "StorageClass"
