import textwrap
import pykube
import json
import pkg_resources
import glob
import os
import yaml
import types

from oslo_serialization import base64

from magnum_cluster_api import objects
from magnum.common.x509 import operations as x509
from magnum.common import neutron
from magnum.common import cert_manager
from oslo_utils import encodeutils

KUBE_TAG = "v1.25.3"
CLOUD_PROVIDER_TAG = "v1.25.3"
CALICO_TAG = "v3.24.2"


class Base:
    def __init__(self, api: pykube.HTTPClient):
        self.api = api

    def apply(self) -> None:
        resource = self.get_object()
        resp = resource.api.patch(
            **resource.api_kwargs(
                headers={
                    "Content-Type": "application/apply-patch+yaml",
                },
                params={
                    "fieldManager": "atmosphere-operator",
                    "force": True,
                },
                data=json.dumps(resource.obj),
            )
        )

        resource.api.raise_for_status(resp)
        resource.set_obj(resp.json())

    def delete(self) -> None:
        resource = self.get_object()
        resource.delete()


class Namespace(Base):
    def get_object(self) -> pykube.Namespace:
        return pykube.Namespace(
            self.api,
            {
                "apiVersion": pykube.Namespace.version,
                "kind": pykube.Namespace.kind,
                "metadata": {
                    "name": "magnum-system",
                },
            },
        )


class ClusterBase(Base):
    def __init__(self, api: pykube.HTTPClient, cluster: any):
        super().__init__(api)
        self.cluster = cluster

    @property
    def labels(self) -> dict:
        return {
            "project-id": self.cluster.project_id,
            "user-id": self.cluster.user_id,
            "cluster-uuid": self.cluster.uuid,
        }


class NodeGroupBase(ClusterBase):
    def __init__(self, api: pykube.HTTPClient, cluster: any, node_group: any):
        super().__init__(api, cluster)
        self.node_group = node_group

    @property
    def labels(self) -> dict:
        return {
            **super().labels,
            **{"node-group-uuid": self.node_group.uuid},
        }


class CloudControllerManagerConfigMap(ClusterBase):
    def get_object(self) -> pykube.ConfigMap:
        version = get_label_value(
            self.cluster, "cloud_provider_tag", CLOUD_PROVIDER_TAG
        )

        manifests_path = pkg_resources.resource_filename(
            "magnum_cluster_api.manifests", "ccm"
        )
        manifests = glob.glob(os.path.join(manifests_path, "*.yaml"))

        return pykube.ConfigMap(
            self.api,
            {
                "apiVersion": pykube.ConfigMap.version,
                "kind": pykube.ConfigMap.kind,
                "metadata": {
                    "name": f"openstack-cloud-controller-manager-{version}",
                    "namespace": "magnum-system",
                },
                "data": {
                    os.path.basename(m): open(m)
                    .read()
                    .replace(
                        "docker.io/k8scloudprovider/openstack-cloud-controller-manager:latest",
                        f"docker.io/k8scloudprovider/openstack-cloud-controller-manager:{version}",
                    )
                    for m in manifests
                },
            },
        )


class CloudControllerManagerClusterResourceSet(ClusterBase):
    def get_object(self) -> objects.ClusterResourceSet:
        version = get_label_value(
            self.cluster, "cloud_provider_tag", CLOUD_PROVIDER_TAG
        )

        return objects.ClusterResourceSet(
            self.api,
            {
                "apiVersion": objects.ClusterResourceSet.version,
                "kind": objects.ClusterResourceSet.kind,
                "metadata": {
                    "name": f"openstack-cloud-controller-manager-{version}",
                    "namespace": "magnum-system",
                },
                "spec": {
                    "clusterSelector": {
                        "matchLabels": {
                            "ccm": f"openstack-cloud-controller-manager-{version}",
                        },
                    },
                    "resources": [
                        {
                            "name": f"openstack-cloud-controller-manager-{version}",
                            "kind": "ConfigMap",
                        },
                    ],
                },
            },
        )


class CalicoConfigMap(ClusterBase):
    def get_object(self) -> pykube.ConfigMap:
        version = get_label_value(self.cluster, "calico_tag", CALICO_TAG)

        manifests_path = pkg_resources.resource_filename(
            "magnum_cluster_api.manifests", "calico"
        )

        return pykube.ConfigMap(
            self.api,
            {
                "apiVersion": pykube.ConfigMap.version,
                "kind": pykube.ConfigMap.kind,
                "metadata": {
                    "name": f"calico-{version}",
                    "namespace": "magnum-system",
                },
                "data": {
                    "calico.yaml": open(
                        os.path.join(manifests_path, f"{version}.yaml")
                    ).read()
                },
            },
        )


class CalicoClusterResourceSet(ClusterBase):
    def get_object(self) -> objects.ClusterResourceSet:
        version = get_label_value(self.cluster, "calico_tag", CALICO_TAG)

        return objects.ClusterResourceSet(
            self.api,
            {
                "apiVersion": objects.ClusterResourceSet.version,
                "kind": objects.ClusterResourceSet.kind,
                "metadata": {
                    "name": f"calico-{version}",
                    "namespace": "magnum-system",
                },
                "spec": {
                    "clusterSelector": {
                        "matchLabels": {
                            "cni": f"calico-{version}",
                        },
                    },
                    "resources": [
                        {
                            "name": f"calico-{version}",
                            "kind": "ConfigMap",
                        },
                    ],
                },
            },
        )


class CertificateAuthoritySecret(ClusterBase):
    def get_object(self) -> pykube.Secret:
        ca_cert = cert_manager.get_backend().CertManager.get_cert(
            getattr(self.cluster, self.REF),
            resource_ref=self.cluster.uuid,
        )

        return pykube.Secret(
            self.api,
            {
                "apiVersion": pykube.Secret.version,
                "kind": pykube.Secret.kind,
                "type": "kubernetes.io/tls",
                "metadata": {
                    "name": f"{name_from_cluster(self.cluster)}-{self.CERT}",
                    "namespace": "magnum-system",
                },
                "stringData": {
                    "tls.crt": encodeutils.safe_decode(ca_cert.get_certificate()),
                    "tls.key": encodeutils.safe_decode(
                        x509.decrypt_key(
                            ca_cert.get_private_key(),
                            ca_cert.get_private_key_passphrase()
                        )
                    ),
                },
            },
        )


class ApiCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "ca"
    REF = "ca_cert_ref"


class EtcdCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "etcd"
    REF = "etcd_ca_cert_ref"


class FrontProxyCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "proxy"
    REF = "front_proxy_ca_cert_ref"


class ServiceAccountCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "sa"
    REF = "magnum_cert_ref"


class CloudConfigSecret(ClusterBase):
    def __init__(
        self,
        api: pykube.HTTPClient,
        cluster: any,
        auth_url: str = None,
        region_name: str = None,
        credential: any = types.SimpleNamespace(id=None, secret=None),
    ):
        super().__init__(api, cluster)
        self.auth_url = auth_url
        self.region_name = region_name
        self.credential = credential

    def get_object(self) -> pykube.Secret:
        return pykube.Secret(
            self.api,
            {
                "apiVersion": pykube.Secret.version,
                "kind": pykube.Secret.kind,
                "metadata": {
                    "name": f"{name_from_cluster(self.cluster)}-cloud-config",
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "stringData": {
                    "cacert": "TODO",  # TODO
                    "clouds.yaml": yaml.dump(
                        {
                            "clouds": {
                                "default": {
                                    "region_name": self.region_name,
                                    "identity_api_version": 3,
                                    "auth": {
                                        "auth_url": self.auth_url,
                                        "application_credential_id": self.credential.id,
                                        "application_credential_secret": self.credential.secret,
                                    },
                                }
                            }
                        }
                    ),
                },
            },
        )


class OpenStackMachineTemplate(NodeGroupBase):
    def get_object(self) -> objects.OpenStackMachineTemplate:
        return objects.OpenStackMachineTemplate(
            self.api,
            {
                "apiVersion": objects.OpenStackMachineTemplate.version,
                "kind": objects.OpenStackMachineTemplate.kind,
                "metadata": {
                    "name": name_from_node_group(self.cluster, self.node_group),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "template": {
                        "spec": {
                            "cloudName": "default",
                            "flavor": self.node_group.flavor_id,
                            "identityRef": {
                                "kind": pykube.Secret.kind,
                                "name": f"{name_from_cluster(self.cluster)}-cloud-config",
                            },
                            "imageUUID": self.node_group.image_id,
                            "sshKeyName": self.cluster.keypair,
                        }
                    }
                },
            },
        )


class KubeadmConfigTemplate(ClusterBase):
    def get_object(self) -> objects.KubeadmConfigTemplate:
        return objects.KubeadmConfigTemplate(
            self.api,
            {
                "apiVersion": objects.KubeadmConfigTemplate.version,
                "kind": objects.KubeadmConfigTemplate.kind,
                "metadata": {
                    "name": name_from_cluster(self.cluster),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "template": {
                        "spec": {
                            "joinConfiguration": {
                                "nodeRegistration": {
                                    "name": "{{ local_hostname }}",
                                    "kubeletExtraArgs": {
                                        "cloud-provider": "external",
                                    },
                                },
                            }
                        }
                    }
                },
            },
        )


class KubeadmControlPlane(NodeGroupBase):
    def __init__(
        self,
        api: pykube.HTTPClient,
        cluster: any,
        node_group: any,
        auth_url: str = None,
        region_name: str = None,
        credential: any = types.SimpleNamespace(id=None, secret=None),
    ):
        super().__init__(api, cluster, node_group)
        self.auth_url = auth_url
        self.region_name = region_name
        self.credential = credential

    def get_object(self) -> objects.KubeadmControlPlane:
        ccm_config = textwrap.dedent(
            f"""\
            [Global]
            auth-url={self.auth_url}
            region={self.region_name}
            application-credential-id={self.credential.id}
            application-credential-secret={self.credential.secret}
            """
        )

        return objects.KubeadmControlPlane(
            self.api,
            {
                "apiVersion": objects.KubeadmControlPlane.version,
                "kind": objects.KubeadmControlPlane.kind,
                "metadata": {
                    "name": name_from_cluster(self.cluster),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "replicas": self.node_group.node_count,
                    "version": get_label_value(self.cluster, "kube_tag", KUBE_TAG),
                    "kubeadmConfigSpec": {
                        "files": [
                            {
                                "path": "/etc/kubernetes/cloud.conf",
                                "owner": "root:root",
                                "permissions": "0600",
                                "content": base64.encode_as_text(ccm_config),
                                "encoding": "base64",
                            },
                        ],
                        "clusterConfiguration": {
                            "apiServer": {
                                "extraArgs": {
                                    "cloud-provider": "external",
                                },
                            },
                            "controllerManager": {
                                "extraArgs": {
                                    "cloud-provider": "external",
                                },
                            },
                        },
                        "initConfiguration": {
                            "nodeRegistration": {
                                "name": "{{ local_hostname }}",
                                "kubeletExtraArgs": {
                                    "cloud-provider": "external",
                                },
                            },
                        },
                        "joinConfiguration": {
                            "nodeRegistration": {
                                "name": "{{ local_hostname }}",
                                "kubeletExtraArgs": {
                                    "cloud-provider": "external",
                                },
                            },
                        },
                    },
                    "machineTemplate": {
                        "infrastructureRef": {
                            "apiVersion": objects.OpenStackMachineTemplate.version,
                            "kind": objects.OpenStackMachineTemplate.kind,
                            "name": name_from_node_group(self.cluster, self.node_group),
                        },
                    },
                },
            },
        )


class MachineDeployment(NodeGroupBase):
    def get_object(self) -> objects.MachineDeployment:
        return objects.MachineDeployment(
            self.api,
            {
                "apiVersion": objects.MachineDeployment.version,
                "kind": objects.MachineDeployment.kind,
                "metadata": {
                    "name": name_from_node_group(self.cluster, self.node_group),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "clusterName": name_from_cluster(self.cluster),
                    "replicas": self.node_group.node_count,
                    "selector": {
                        "matchLabels": None,
                    },
                    "template": {
                        "spec": {
                            "clusterName": name_from_cluster(self.cluster),
                            "bootstrap": {
                                "configRef": {
                                    "apiVersion": objects.KubeadmConfigTemplate.version,
                                    "kind": objects.KubeadmConfigTemplate.kind,
                                    "name": name_from_cluster(self.cluster),
                                },
                            },
                            "version": get_label_value(
                                self.cluster, "kube_tag", KUBE_TAG
                            ),
                            "failureDomain": get_label_value(
                                self.cluster, "availability_zone", ""
                            ),
                            "infrastructureRef": {
                                "apiVersion": objects.OpenStackMachineTemplate.version,
                                "kind": objects.OpenStackMachineTemplate.kind,
                                "name": name_from_node_group(self.cluster, self.node_group),
                            },
                        }
                    },
                },
            },
        )


class OpenStackCluster(ClusterBase):
    def __init__(self, api: pykube.HTTPClient, cluster: any, context: any):
        super().__init__(api, cluster)
        self.context = context

    def get_object(self) -> objects.OpenStackCluster:
        external_network = self.cluster.cluster_template.external_network_id

        return objects.OpenStackCluster(
            self.api,
            {
                "apiVersion": objects.OpenStackCluster.version,
                "kind": objects.OpenStackCluster.kind,
                "metadata": {
                    "name": name_from_cluster(self.cluster),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "cloudName": "default",
                    "apiServerLoadBalancer": {
                        "enabled": self.cluster.master_lb_enabled,
                    },
                    "dnsNameservers": self.cluster.cluster_template.dns_nameserver.split(
                        ","
                    ),
                    "externalNetworkId": neutron.get_external_network_id(
                        self.context, external_network
                    ),
                    "identityRef": {
                        "kind": pykube.Secret.kind,
                        "name": f"{name_from_cluster(self.cluster)}-cloud-config",
                    },
                    "managedSecurityGroups": True,
                    "nodeCidr": get_label_value(
                        self.cluster, "fixed_subnet_cidr", "10.6.0.0/24"
                    ),
                },
            },
        )


class Cluster(ClusterBase):
    @property
    def labels(self) -> dict:
        ccm_version = get_label_value(
            self.cluster, "cloud_provider_tag", CLOUD_PROVIDER_TAG
        )
        cni_verison = get_label_value(self.cluster, "calico_tag", CALICO_TAG)

        return {
            **super().labels,
            **{
                "cni": f"calico-{cni_verison}",
                "ccm": f"openstack-cloud-controller-manager-{ccm_version}",
            },
        }

    def get_object(self) -> objects.Cluster:
        return objects.Cluster(
            self.api,
            {
                "apiVersion": objects.Cluster.version,
                "kind": objects.Cluster.kind,
                "metadata": {
                    "name": name_from_cluster(self.cluster),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "clusterNetwork": {
                        "serviceDomain": get_label_value(
                            self.cluster, "dns_cluster_domain", "cluster.local"
                        ),
                        "pods": {
                            "cidrBlocks": [
                                get_label_value(
                                    self.cluster, "calico_ipv4pool", "10.100.0.0/16"
                                )
                            ],
                        },
                    },
                    "controlPlaneRef": {
                        "apiVersion": objects.KubeadmControlPlane.version,
                        "kind": objects.KubeadmControlPlane.kind,
                        "name": name_from_cluster(self.cluster),
                    },
                    "infrastructureRef": {
                        "apiVersion": objects.OpenStackCluster.version,
                        "kind": objects.OpenStackCluster.kind,
                        "name": name_from_cluster(self.cluster),
                    },
                },
            },
        )


def get_label_value(cluster: any, key: str, default: str) -> str:
    return cluster.labels.get(key, cluster.cluster_template.labels.get(key, default))


def name_from_cluster(cluster: any) -> str:
    return cluster.uuid


def name_from_node_group(cluster: any, node_group: any) -> str:
    return f"{name_from_cluster(cluster)}-{node_group.name}"
