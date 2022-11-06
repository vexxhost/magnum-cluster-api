import pykube


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


class KubeadmControlPlaneTemplate(pykube.objects.NamespacedAPIObject):
    version = "controlplane.cluster.x-k8s.io/v1beta1"
    endpoint = "kubeadmcontrolplanetemplates"
    kind = "KubeadmControlPlaneTemplate"


class Machine(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machines"
    kind = "Machine"


class MachineHealthCheck(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machinehealthchecks"
    kind = "MachineHealthCheck"


class OpenStackClusterTemplate(pykube.objects.NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1alpha6"
    endpoint = "openstackclustertemplates"
    kind = "OpenStackClusterTemplate"


class ClusterClass(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusterclasses"
    kind = "ClusterClass"


class Cluster(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusters"
    kind = "Cluster"
