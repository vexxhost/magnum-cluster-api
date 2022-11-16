import glob
import json
import os
import textwrap
import types

import pkg_resources
import pykube
import yaml
from magnum import objects as magnum_objects
from magnum.common import cert_manager, cinder, context, neutron
from magnum.common.x509 import operations as x509
from oslo_config import cfg
from oslo_serialization import base64
from oslo_utils import encodeutils

from magnum_cluster_api import clients, objects, utils

CONF = cfg.CONF
KUBE_TAG = "v1.25.3"
CLOUD_PROVIDER_TAG = "v1.25.3"
CALICO_TAG = "v3.24.2"
AUTOSCALER_HELM_CHART_VERSION = "9.21.0"
CSI_TAG = "v1.25.3"

CLUSTER_CLASS_VERSION = pkg_resources.require("magnum_cluster_api")[0].version
CLUSTER_CLASS_NAME = f"magnum-v{CLUSTER_CLASS_VERSION}"

CLUSTER_UPGRADE_LABELS = {"kube_tag"}

PLACEHOLDER = "PLACEHOLDER"


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


class ClusterAutoscalerHelmRepository(Base):
    def get_object(self) -> objects.HelmRepository:
        return objects.HelmRepository(
            self.api,
            {
                "apiVersion": objects.HelmRepository.version,
                "kind": objects.HelmRepository.kind,
                "metadata": {
                    "name": "autoscaler",
                    "namespace": "magnum-system",
                },
                "spec": {
                    "interval": "1m",
                    "url": "https://kubernetes.github.io/autoscaler",
                },
            },
        )


class ClusterAutoscalerHelmRelease(ClusterBase):
    def get_object(self) -> objects.HelmRelease:
        cluster_name = utils.get_or_generate_cluster_api_name(self.api, self.cluster)
        return objects.HelmRelease(
            self.api,
            {
                "apiVersion": objects.HelmRelease.version,
                "kind": objects.HelmRelease.kind,
                "metadata": {
                    "name": cluster_name,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "interval": "60s",
                    "chart": {
                        "spec": {
                            "chart": "cluster-autoscaler",
                            "version": AUTOSCALER_HELM_CHART_VERSION,
                            "sourceRef": {
                                "kind": objects.HelmRepository.kind,
                                "name": "autoscaler",
                            },
                        },
                    },
                    "values": {
                        "fullnameOverride": f"{cluster_name}-autoscaler",
                        "cloudProvider": "clusterapi",
                        "clusterAPIMode": "kubeconfig-incluster",
                        "clusterAPIKubeconfigSecret": f"{cluster_name}-kubeconfig",
                        "autoDiscovery": {
                            "clusterName": cluster_name,
                        },
                        "nodeSelector": {
                            "openstack-control-plane": "enabled",
                        },
                    },
                },
            },
        )


class ClusterResourcesConfigMap(ClusterBase):
    def __init__(
        self,
        context: context.RequestContext,
        api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
    ):
        self.context = context
        self.api = api
        self.cluster = cluster

    def get_object(self) -> pykube.ConfigMap:
        # NOTE(mnaser): We have to assert that the only CNI we support is Calico.
        assert CONF.cluster_template.kubernetes_allowed_network_drivers == ["calico"]

        manifests_path = pkg_resources.resource_filename(
            "magnum_cluster_api", "manifests"
        )
        calico_version = utils.get_cluster_label(self.cluster, "calico_tag", CALICO_TAG)
        ccm_version = utils.get_cluster_label(
            self.cluster, "cloud_provider_tag", CLOUD_PROVIDER_TAG
        )
        csi_version = utils.get_cluster_label(
            self.cluster, "cinder_csi_plugin_tag", CSI_TAG
        )

        repository = utils.get_cluster_label(
            self.cluster,
            "container_infra_prefix",
            "quay.io/vexxhost",
        )

        osc = clients.get_openstack_api(self.context)
        volume_types = osc.cinder().volume_types.list()
        default_volume_type = osc.cinder().volume_types.default()

        return pykube.ConfigMap(
            self.api,
            {
                "apiVersion": pykube.ConfigMap.version,
                "kind": pykube.ConfigMap.kind,
                "metadata": {
                    "name": self.cluster.uuid,
                    "namespace": "magnum-system",
                },
                "data": {
                    **{
                        os.path.basename(manifest): utils.update_manifest_images(
                            self.cluster,
                            manifest,
                            repository=repository,
                            replacements=[
                                (
                                    "docker.io/k8scloudprovider/openstack-cloud-controller-manager:latest",
                                    f"docker.io/k8scloudprovider/openstack-cloud-controller-manager:{ccm_version}",
                                ),
                            ],
                        )
                        for manifest in glob.glob(
                            os.path.join(manifests_path, "ccm/*.yaml")
                        )
                    },
                    **{
                        os.path.basename(manifest): utils.update_manifest_images(
                            self.cluster,
                            manifest,
                            repository=repository,
                            replacements=[
                                (
                                    "docker.io/k8scloudprovider/cinder-csi-plugin:latest",
                                    f"docker.io/k8scloudprovider/cinder-csi-plugin:{csi_version}",
                                ),
                            ],
                        )
                        for manifest in glob.glob(
                            os.path.join(manifests_path, "csi/*.yaml")
                        )
                    },
                    **{
                        "calico.yml": utils.update_manifest_images(
                            self.cluster,
                            os.path.join(
                                manifests_path, f"calico/{calico_version}.yaml"
                            ),
                            repository=repository,
                        )
                    },
                    **{
                        f"storageclass-{vt.name}.yaml": yaml.dump(
                            {
                                "apiVersion": objects.StorageClass.version,
                                "kind": objects.StorageClass.kind,
                                "metadata": {
                                    "annotations": {
                                        "storageclass.kubernetes.io/is-default-class": "true"
                                    }
                                    if default_volume_type.name == vt.name
                                    else {},
                                    "name": vt.name,
                                },
                                "provisioner": "kubernetes.io/cinder",
                                "parameters": {
                                    "type": vt.name,
                                },
                                "reclaimPolicy": "Delete",
                                "volumeBindingMode": "Immediate",
                            }
                        )
                        for vt in volume_types
                        if vt.name != "__DEFAULT__"
                    },
                },
            },
        )

    def get_or_none(self) -> objects.Cluster:
        return pykube.ConfigMap.objects(
            self.api, namespace="magnum-system"
        ).get_or_none(name=self.cluster.uuid)

    def delete(self):
        cr_cm = self.get_or_none()
        if cr_cm:
            cr_cm.delete()


class ClusterResourceSet(ClusterBase):
    def get_object(self) -> objects.ClusterResourceSet:
        return objects.ClusterResourceSet(
            self.api,
            {
                "apiVersion": objects.ClusterResourceSet.version,
                "kind": objects.ClusterResourceSet.kind,
                "metadata": {
                    "name": self.cluster.uuid,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "clusterSelector": {
                        "matchLabels": {
                            "cluster-uuid": self.cluster.uuid,
                        },
                    },
                    "resources": [
                        {
                            "name": self.cluster.uuid,
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
                    "name": f"{utils.get_or_generate_cluster_api_name(self.api, self.cluster)}-{self.CERT}",
                    "namespace": "magnum-system",
                },
                "stringData": {
                    "tls.crt": encodeutils.safe_decode(ca_cert.get_certificate()),
                    "tls.key": encodeutils.safe_decode(
                        x509.decrypt_key(
                            ca_cert.get_private_key(),
                            ca_cert.get_private_key_passphrase(),
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
                    "name": utils.get_or_generate_cluster_api_cloud_config_secret_name(
                        self.api, self.cluster
                    ),
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


class KubeadmControlPlaneTemplate(Base):
    def get_object(self) -> objects.KubeadmControlPlaneTemplate:
        manifests_path = pkg_resources.resource_filename(
            "magnum_cluster_api.manifests", "audit"
        )
        audit_policy = open(os.path.join(manifests_path, "policy.yaml")).read()

        return objects.KubeadmControlPlaneTemplate(
            self.api,
            {
                "apiVersion": objects.KubeadmControlPlaneTemplate.version,
                "kind": objects.KubeadmControlPlaneTemplate.kind,
                "metadata": {
                    "name": CLUSTER_CLASS_NAME,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "template": {
                        "spec": {
                            "kubeadmConfigSpec": {
                                "clusterConfiguration": {
                                    "apiServer": {
                                        "extraArgs": {
                                            "cloud-provider": "external",
                                            "profiling": "false",
                                        },
                                        "extraVolumes": [],
                                    },
                                    "controllerManager": {
                                        "extraArgs": {
                                            "cloud-provider": "external",
                                            "profiling": "false",
                                        },
                                    },
                                    "scheduler": {
                                        "extraArgs": {
                                            "profiling": "false",
                                        },
                                    },
                                },
                                "files": [
                                    {
                                        "path": "/etc/kubernetes/audit-policy/apiserver-audit-policy.yaml",
                                        "permissions": "0600",
                                        "content": base64.encode_as_text(audit_policy),
                                        "encoding": "base64",
                                    },
                                ],
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
                        },
                    },
                },
            },
        )


class KubeadmConfigTemplate(Base):
    def get_object(self) -> objects.KubeadmConfigTemplate:
        return objects.KubeadmConfigTemplate(
            self.api,
            {
                "apiVersion": objects.KubeadmConfigTemplate.version,
                "kind": objects.KubeadmConfigTemplate.kind,
                "metadata": {
                    "name": CLUSTER_CLASS_NAME,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "template": {
                        "spec": {
                            "files": [],
                            "joinConfiguration": {
                                "nodeRegistration": {
                                    "name": "{{ local_hostname }}",
                                    "kubeletExtraArgs": {
                                        "cloud-provider": "external",
                                    },
                                },
                            },
                        }
                    }
                },
            },
        )


class OpenStackMachineTemplate(Base):
    def get_object(self) -> objects.OpenStackMachineTemplate:
        return objects.OpenStackMachineTemplate(
            self.api,
            {
                "apiVersion": objects.OpenStackMachineTemplate.version,
                "kind": objects.OpenStackMachineTemplate.kind,
                "metadata": {
                    "name": CLUSTER_CLASS_NAME,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "template": {
                        "spec": {"cloudName": "default", "flavor": PLACEHOLDER}
                    }
                },
            },
        )


class OpenStackClusterTemplate(Base):
    def get_object(self) -> objects.OpenStackClusterTemplate:
        return objects.OpenStackClusterTemplate(
            self.api,
            {
                "apiVersion": objects.OpenStackClusterTemplate.version,
                "kind": objects.OpenStackClusterTemplate.kind,
                "metadata": {
                    "name": CLUSTER_CLASS_NAME,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "template": {
                        "spec": {
                            "cloudName": "default",
                            "managedSecurityGroups": True,
                        },
                    },
                },
            },
        )


class ClusterClass(Base):
    def get_object(self) -> objects.ClusterClass:
        return objects.ClusterClass(
            self.api,
            {
                "apiVersion": objects.ClusterClass.version,
                "kind": objects.ClusterClass.kind,
                "metadata": {
                    "name": CLUSTER_CLASS_NAME,
                    "namespace": "magnum-system",
                },
                "spec": {
                    "controlPlane": {
                        "ref": {
                            "apiVersion": objects.KubeadmControlPlaneTemplate.version,
                            "kind": objects.KubeadmControlPlaneTemplate.kind,
                            "name": CLUSTER_CLASS_NAME,
                        },
                        "machineInfrastructure": {
                            "ref": {
                                "apiVersion": objects.OpenStackMachineTemplate.version,
                                "kind": objects.OpenStackMachineTemplate.kind,
                                "name": CLUSTER_CLASS_NAME,
                            },
                        },
                        "machineHealthCheck": {
                            "maxUnhealthy": "33%",
                            "unhealthyConditions": [
                                {
                                    "type": "Ready",
                                    "status": "False",
                                    "timeout": "5m",
                                },
                                {
                                    "type": "Ready",
                                    "status": "Unknown",
                                    "timeout": "5m",
                                },
                            ],
                        },
                    },
                    "infrastructure": {
                        "ref": {
                            "apiVersion": objects.OpenStackClusterTemplate.version,
                            "kind": objects.OpenStackClusterTemplate.kind,
                            "name": CLUSTER_CLASS_NAME,
                        },
                    },
                    "workers": {
                        "machineDeployments": [
                            {
                                "class": "default-worker",
                                "template": {
                                    "bootstrap": {
                                        "ref": {
                                            "apiVersion": objects.KubeadmConfigTemplate.version,
                                            "kind": objects.KubeadmConfigTemplate.kind,
                                            "name": CLUSTER_CLASS_NAME,
                                        }
                                    },
                                    "infrastructure": {
                                        "ref": {
                                            "apiVersion": objects.OpenStackMachineTemplate.version,
                                            "kind": objects.OpenStackMachineTemplate.kind,
                                            "name": CLUSTER_CLASS_NAME,
                                        }
                                    },
                                },
                                "machineHealthCheck": {
                                    "maxUnhealthy": "33%",
                                    "unhealthyConditions": [
                                        {
                                            "type": "Ready",
                                            "status": "False",
                                            "timeout": "5m",
                                        },
                                        {
                                            "type": "Ready",
                                            "status": "Unknown",
                                            "timeout": "5m",
                                        },
                                    ],
                                },
                            }
                        ],
                    },
                    "variables": [
                        {
                            "name": "apiServerLoadBalancer",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "object",
                                    "required": ["enabled"],
                                    "properties": {
                                        "enabled": {
                                            "type": "boolean",
                                        },
                                    },
                                },
                            },
                        },
                        {
                            "name": "auditLog",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "object",
                                    "required": [
                                        "enabled",
                                        "maxAge",
                                        "maxBackup",
                                        "maxSize",
                                    ],
                                    "properties": {
                                        "enabled": {
                                            "type": "boolean",
                                        },
                                        "maxAge": {
                                            "type": "string",
                                        },
                                        "maxBackup": {
                                            "type": "string",
                                        },
                                        "maxSize": {
                                            "type": "string",
                                        },
                                    },
                                },
                            },
                        },
                        {
                            "name": "bootVolume",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "object",
                                    "required": ["size"],
                                    "properties": {
                                        "size": {
                                            "type": "integer",
                                        },
                                        "type": {
                                            "type": "string",
                                        },
                                    },
                                },
                            },
                        },
                        {
                            "name": "clusterIdentityRef",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "object",
                                    "required": ["kind", "name"],
                                    "properties": {
                                        "kind": {
                                            "type": "string",
                                            "enum": [pykube.Secret.kind],
                                        },
                                        "name": {"type": "string"},
                                    },
                                },
                            },
                        },
                        {
                            "name": "cloudControllerManagerConfig",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "controlPlaneFlavor",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "dnsNameservers",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                    },
                                },
                            },
                        },
                        {
                            "name": "externalNetworkId",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "flavor",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "imageRepository",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "imageUUID",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "nodeCidr",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "sshKeyName",
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                    ],
                    "patches": [
                        {
                            "name": "auditLog",
                            "enabledIf": "{{ if .auditLog.enabled }}true{{end}}",
                            "definitions": [
                                {
                                    "selector": {
                                        "apiVersion": objects.KubeadmControlPlaneTemplate.version,
                                        "kind": objects.KubeadmControlPlaneTemplate.kind,
                                        "matchResources": {
                                            "controlPlane": True,
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-path",  # noqa: E501
                                            "value": "/var/log/audit/kube-apiserver-audit.log",
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-maxage",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "auditLog.maxAge",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-maxbackup",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "auditLog.maxBackup",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-log-maxsize",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "auditLog.maxSize",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/audit-policy-file",  # noqa: E501
                                            "value": "/etc/kubernetes/audit-policy/apiserver-audit-policy.yaml",
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraVolumes",  # noqa: E501
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    - name: audit-policy
                                                      hostPath: /etc/kubernetes/audit-policy
                                                      mountPath: /etc/kubernetes/audit-policy
                                                    - name: audit-logs
                                                      hostPath: /var/log/kubernetes/audit
                                                      mountPath: /var/log/audit
                                                    """
                                                ),
                                            },
                                        },
                                    ],
                                }
                            ],
                        },
                        {
                            "name": "bootVolume",
                            "enabledIf": "{{ if gt .bootVolume.size 0.0 }}true{{end}}",
                            "definitions": [
                                {
                                    "selector": {
                                        "apiVersion": objects.OpenStackMachineTemplate.version,
                                        "kind": objects.OpenStackMachineTemplate.kind,
                                        "matchResources": {
                                            "controlPlane": True,
                                            "machineDeploymentClass": {
                                                "names": ["default-worker"],
                                            },
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/rootVolume",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    diskSize: {{ .bootVolume.size }}
                                                    volumeType: {{ .bootVolume.type }}
                                                    """
                                                ),
                                            },
                                        },
                                    ],
                                }
                            ],
                        },
                        {
                            "name": "clusterConfig",
                            "definitions": [
                                {
                                    "selector": {
                                        "apiVersion": objects.OpenStackMachineTemplate.version,
                                        "kind": objects.OpenStackMachineTemplate.kind,
                                        "matchResources": {
                                            "controlPlane": True,
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/flavor",
                                            "valueFrom": {
                                                "variable": "controlPlaneFlavor",
                                            },
                                        },
                                    ],
                                },
                                {
                                    "selector": {
                                        "apiVersion": objects.OpenStackMachineTemplate.version,
                                        "kind": objects.OpenStackMachineTemplate.kind,
                                        "matchResources": {
                                            "machineDeploymentClass": {
                                                "names": ["default-worker"],
                                            },
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/flavor",
                                            "valueFrom": {
                                                "variable": "flavor",
                                            },
                                        },
                                    ],
                                },
                                {
                                    "selector": {
                                        "apiVersion": objects.OpenStackMachineTemplate.version,
                                        "kind": objects.OpenStackMachineTemplate.kind,
                                        "matchResources": {
                                            "controlPlane": True,
                                            "machineDeploymentClass": {
                                                "names": ["default-worker"],
                                            },
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/identityRef",
                                            "valueFrom": {
                                                "variable": "clusterIdentityRef"
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/sshKeyName",
                                            "valueFrom": {"variable": "sshKeyName"},
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/imageUUID",
                                            "valueFrom": {"variable": "imageUUID"},
                                        },
                                    ],
                                },
                                {
                                    "selector": {
                                        "apiVersion": objects.OpenStackClusterTemplate.version,
                                        "kind": objects.OpenStackClusterTemplate.kind,
                                        "matchResources": {
                                            "infrastructureCluster": True,
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/apiServerLoadBalancer",
                                            "valueFrom": {
                                                "variable": "apiServerLoadBalancer"
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/identityRef",
                                            "valueFrom": {
                                                "variable": "clusterIdentityRef"
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/dnsNameservers",
                                            "valueFrom": {"variable": "dnsNameservers"},
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/externalNetworkId",
                                            "valueFrom": {
                                                "variable": "externalNetworkId"
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/nodeCidr",
                                            "valueFrom": {"variable": "nodeCidr"},
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "controlPlaneConfig",
                            "definitions": [
                                {
                                    "selector": {
                                        "apiVersion": objects.KubeadmControlPlaneTemplate.version,
                                        "kind": objects.KubeadmControlPlaneTemplate.kind,
                                        "matchResources": {
                                            "controlPlane": True,
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/imageRepository",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "imageRepository",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/kubernetes/cloud.conf"
                                                    owner: "root:root"
                                                    permissions: "0600"
                                                    content: "{{ .cloudControllerManagerConfig }}"
                                                    encoding: "base64"
                                                    """
                                                ),
                                            },
                                        },
                                    ],
                                },
                                {
                                    "selector": {
                                        "apiVersion": objects.KubeadmConfigTemplate.version,
                                        "kind": objects.KubeadmConfigTemplate.kind,
                                        "matchResources": {
                                            "machineDeploymentClass": {
                                                "names": ["default-worker"],
                                            }
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/clusterConfiguration",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    imageRepository: "{{ .imageRepository }}"
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/files",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    - path: "/etc/kubernetes/cloud.conf"
                                                      owner: "root:root"
                                                      permissions: "0600"
                                                      content: "{{ .cloudControllerManagerConfig }}"
                                                      encoding: "base64"
                                                """
                                                ),
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                },
            },
        )


def create_cluster_class(
    api: pykube.HTTPClient,
) -> ClusterClass:
    """
    Create a ClusterClass and all of it's supporting resources from a Magnum
    cluster template using server-side apply.
    """

    KubeadmControlPlaneTemplate(api).apply()
    KubeadmConfigTemplate(api).apply()
    OpenStackMachineTemplate(api).apply()
    OpenStackClusterTemplate(api).apply()
    ClusterClass(api).apply()


class Cluster(ClusterBase):
    def __init__(
        self,
        context: context.RequestContext,
        api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
    ):
        self.context = context
        self.api = api
        self.cluster = cluster

    @property
    def labels(self) -> dict:
        ccm_version = utils.get_cluster_label(
            self.cluster, "cloud_provider_tag", CLOUD_PROVIDER_TAG
        )
        cni_verison = utils.get_cluster_label(self.cluster, "calico_tag", CALICO_TAG)

        labels = {
            "cni": f"calico-{cni_verison}",
            "ccm": f"openstack-cloud-controller-manager-{ccm_version}",
        }

        if utils.get_cluster_label_as_bool(self.cluster, "cinder_csi_enabled", True):
            csi_version = utils.get_cluster_label(
                self.cluster, "cinder_csi_plugin_tag", CSI_TAG
            )
            labels["csi"] = "cinder"
            labels["cinder-csi-version"] = csi_version

        return {**super().labels, **labels}

    def get_or_none(self) -> objects.Cluster:
        return objects.Cluster.objects(self.api, namespace="magnum-system").get_or_none(
            name=utils.get_or_generate_cluster_api_name(self.api, self.cluster)
        )

    def get_object(self) -> objects.Cluster:
        auto_scaling_enabled = utils.get_cluster_label_as_bool(
            self.cluster, "auto_scaling_enabled", False
        )
        return objects.Cluster(
            self.api,
            {
                "apiVersion": objects.Cluster.version,
                "kind": objects.Cluster.kind,
                "metadata": {
                    "name": utils.get_or_generate_cluster_api_name(
                        self.api, self.cluster
                    ),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "spec": {
                    "clusterNetwork": {
                        "serviceDomain": utils.get_cluster_label(
                            self.cluster,
                            "dns_cluster_domain",
                            "cluster.local",
                        ),
                        "pods": {
                            "cidrBlocks": [
                                utils.get_cluster_label(
                                    self.cluster,
                                    "calico_ipv4pool",
                                    "10.100.0.0/16",
                                )
                            ],
                        },
                    },
                    "topology": {
                        "class": CLUSTER_CLASS_NAME,
                        "version": utils.get_cluster_label(
                            self.cluster, "kube_tag", KUBE_TAG
                        ),
                        "controlPlane": {
                            "replicas": self.cluster.master_count,
                            "machineHealthCheck": {
                                "enable": utils.get_cluster_label_as_bool(
                                    self.cluster, "auto_healing_enabled", True
                                )
                            },
                        },
                        "workers": {
                            "machineDeployments": [
                                {
                                    "class": "default-worker",
                                    "name": ng.name,
                                    "replicas": None
                                    if auto_scaling_enabled
                                    else ng.node_count,
                                    "metadata": {
                                        "annotations": {
                                            "cluster.x-k8s.io/cluster-api-autoscaler-node-group-min-size": f"{utils.get_node_group_min_node_count(ng)}",  # noqa: E501
                                            "cluster.x-k8s.io/cluster-api-autoscaler-node-group-max-size": f"{utils.get_node_group_max_node_count(ng)}",  # noqa: E501
                                        }
                                    }
                                    if auto_scaling_enabled
                                    else {},
                                    "failureDomain": utils.get_cluster_label(
                                        self.cluster, "availability_zone", ""
                                    ),
                                    "machineHealthCheck": {
                                        "enable": utils.get_cluster_label_as_bool(
                                            self.cluster, "auto_healing_enabled", True
                                        )
                                    },
                                    "variables": {
                                        "overrides": [
                                            {
                                                "name": "bootVolume",
                                                "value": {
                                                    "size": utils.get_node_group_label_as_int(
                                                        self.context,
                                                        ng,
                                                        "boot_volume_size",
                                                        CONF.cinder.default_boot_volume_size,
                                                    ),
                                                    "type": utils.get_node_group_label(
                                                        self.context,
                                                        ng,
                                                        "boot_volume_type",
                                                        cinder.get_default_boot_volume_type(
                                                            self.context
                                                        ),
                                                    ),
                                                },
                                            },
                                            {
                                                "name": "flavor",
                                                "value": ng.flavor_id,
                                            },
                                            {
                                                "name": "imageRepository",
                                                "value": utils.get_node_group_label(
                                                    self.context,
                                                    ng,
                                                    "container_infra_prefix",
                                                    "quay.io/vexxhost",
                                                ),
                                            },
                                            {
                                                "name": "imageUUID",
                                                "value": ng.image_id,
                                            },
                                        ],
                                    },
                                }
                                for ng in self.cluster.nodegroups
                                if ng.role != "master"
                            ]
                        },
                        "variables": [
                            {
                                "name": "apiServerLoadBalancer",
                                "value": {
                                    "enabled": self.cluster.master_lb_enabled,
                                },
                            },
                            {
                                "name": "auditLog",
                                "value": {
                                    "enabled": utils.get_cluster_label_as_bool(
                                        self.cluster, "audit_log_enabled", False
                                    ),
                                    "maxAge": utils.get_cluster_label(
                                        self.cluster, "audit_log_max_age", "30"
                                    ),
                                    "maxBackup": utils.get_cluster_label(
                                        self.cluster, "audit_log_max_backup", "10"
                                    ),
                                    "maxSize": utils.get_cluster_label(
                                        self.cluster, "audit_log_max_size", "100"
                                    ),
                                },
                            },
                            {
                                "name": "bootVolume",
                                "value": {
                                    "size": utils.get_cluster_label_as_int(
                                        self.cluster,
                                        "boot_volume_size",
                                        CONF.cinder.default_boot_volume_size,
                                    ),
                                    "type": utils.get_cluster_label(
                                        self.cluster,
                                        "boot_volume_type",
                                        cinder.get_default_boot_volume_type(
                                            self.context
                                        ),
                                    ),
                                },
                            },
                            {
                                "name": "clusterIdentityRef",
                                "value": {
                                    "kind": pykube.Secret.kind,
                                    "name": utils.get_or_generate_cluster_api_cloud_config_secret_name(
                                        self.api, self.cluster
                                    ),
                                },
                            },
                            {
                                "name": "cloudControllerManagerConfig",
                                "value": base64.encode_as_text(
                                    utils.generate_cloud_controller_manager_config(
                                        self.api, self.cluster
                                    )
                                ),
                            },
                            {
                                "name": "controlPlaneFlavor",
                                "value": self.cluster.master_flavor_id,
                            },
                            {
                                "name": "dnsNameservers",
                                "value": self.cluster.cluster_template.dns_nameserver.split(
                                    ","
                                ),
                            },
                            {
                                "name": "externalNetworkId",
                                "value": neutron.get_external_network_id(
                                    self.context,
                                    self.cluster.cluster_template.external_network_id,
                                ),
                            },
                            {
                                "name": "flavor",
                                "value": self.cluster.flavor_id,
                            },
                            {
                                "name": "imageRepository",
                                "value": utils.get_cluster_label(
                                    self.cluster,
                                    "container_infra_prefix",
                                    "quay.io/vexxhost",
                                ),
                            },
                            {
                                "name": "imageUUID",
                                "value": self.cluster.default_ng_master.image_id,
                            },
                            {
                                "name": "nodeCidr",
                                "value": utils.get_cluster_label(
                                    self.cluster,
                                    "fixed_subnet_cidr",
                                    "10.6.0.0/24",
                                ),
                            },
                            {
                                "name": "sshKeyName",
                                "value": self.cluster.keypair or "",
                            },
                        ],
                    },
                },
            },
        )

    def delete(self):
        capi_cluster = self.get_or_none()
        if capi_cluster:
            capi_cluster.delete()


def set_autoscaler_metadata_in_machinedeployment(
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
    nodegroup: magnum_objects.NodeGroup,
):
    # Set autoscaler annotations to MachineDeployment(MD)s because annotations in Cluster topology
    # are not propogated to MDs. Upstream issue:  https://github.com/kubernetes-sigs/cluster-api/pull/7088

    if not utils.get_cluster_label_as_bool(cluster, "auto_scaling_enabled", False):
        return
    mds = objects.MachineDeployment.objects(api).filter(
        namespace="magnum-system",
        selector={
            "cluster.x-k8s.io/cluster-name": utils.get_or_generate_cluster_api_name(
                api, cluster
            ),
            "topology.cluster.x-k8s.io/deployment-name": nodegroup.name,
        },
    )
    for md in mds:
        md.obj["metadata"]["annotations"][
            "cluster.x-k8s.io/cluster-api-autoscaler-node-group-max-size"
        ] = f"{utils.get_node_group_max_node_count(nodegroup)}"
        md.obj["metadata"]["annotations"][
            "cluster.x-k8s.io/cluster-api-autoscaler-node-group-min-size"
        ] = f"{utils.get_node_group_min_node_count(nodegroup)}"
        md.update()


def apply_cluster_from_magnum_cluster(
    context: context.RequestContext,
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
    cluster_template: magnum_objects.ClusterTemplate = None,
) -> objects.Cluster:
    """
    Create a ClusterAPI cluster given a Magnum Cluster object.
    """
    create_cluster_class(api)

    if cluster_template is None:
        cluster_template = cluster.cluster_template

    # NOTE(mnaser): When using Cluster API, there is a 1:1 mapping between image
    #               and version of Kubernetes, therefore, we need to ignore the
    #               `image_id` field, as well as copy over any tags relating to
    #               the Kubernetes version.
    #
    #               I hate this.
    for label in CLUSTER_UPGRADE_LABELS:
        cluster.labels[label] = cluster_template.labels[label]
        for ng in cluster.nodegroups:
            ng.image_id = cluster_template.image_id
            ng.labels[label] = cluster_template.labels[label]
            ng.save()
    cluster.save()

    ClusterResourcesConfigMap(context, api, cluster).apply()
    ClusterResourceSet(api, cluster).apply()
    Cluster(context, api, cluster).apply()
    ClusterAutoscalerHelmRepository(api).apply()
    if utils.get_cluster_label_as_bool(cluster, "auto_scaling_enabled", False):
        ClusterAutoscalerHelmRelease(api, cluster).apply()


def get_kubeadm_control_plane(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> objects.KubeadmControlPlane:
    kcps = objects.KubeadmControlPlane.objects(api, namespace="magnum-system").filter(
        selector={
            "cluster.x-k8s.io/cluster-name": utils.get_or_generate_cluster_api_name(
                api, cluster
            )
        },
    )
    if len(kcps) == 1:
        return list(kcps)[0]
    return None


def get_machine_deployment(
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
    node_group: magnum_objects.NodeGroup,
) -> objects.KubeadmControlPlane:
    mds = objects.MachineDeployment.objects(api, namespace="magnum-system").filter(
        selector={
            "cluster.x-k8s.io/cluster-name": utils.get_or_generate_cluster_api_name(
                api, cluster
            ),
            "topology.cluster.x-k8s.io/deployment-name": node_group.name,
        },
    )
    if len(mds) == 1:
        return list(mds)[0]
    return None
