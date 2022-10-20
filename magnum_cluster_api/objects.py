import pykube


class ClusterResourceSet(pykube.objects.NamespacedAPIObject):
    version = "addons.cluster.x-k8s.io/v1beta1"
    endpoint = "clusterresourcesets"
    kind = "ClusterResourceSet"


class OpenStackMachineTemplate(pykube.objects.NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1alpha5"
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


class MachineDeployment(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "machinedeployments"
    kind = "MachineDeployment"


class OpenStackCluster(pykube.objects.NamespacedAPIObject):
    version = "infrastructure.cluster.x-k8s.io/v1alpha5"
    endpoint = "openstackclusters"
    kind = "OpenStackCluster"


class Cluster(pykube.objects.NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta1"
    endpoint = "clusters"
    kind = "Cluster"
