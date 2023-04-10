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

import pykube


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


class ClusterClass(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusterclasses"
    kind = "ClusterClass"


class Cluster(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusters"
    kind = "Cluster"


class StorageClass(pykube.objects.APIObject):
    version = "storage.k8s.io/v1"
    endpoint = "storageclasses"
    kind = "StorageClass"
