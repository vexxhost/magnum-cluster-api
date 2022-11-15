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


class HelmRelease(pykube.objects.NamespacedAPIObject):
    version = "helm.toolkit.fluxcd.io/v2beta1"
    endpoint = "helmreleases"
    kind = "HelmRelease"


class HelmRepository(pykube.objects.NamespacedAPIObject):
    version = "source.toolkit.fluxcd.io/v1beta2"
    endpoint = "helmrepositories"
    kind = "HelmRepository"
