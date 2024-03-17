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

import glob
import json
import os
import textwrap
import types

import certifi
import pkg_resources
import pykube
import yaml
from magnum import objects as magnum_objects
from magnum.common import context, neutron
from magnum.common.cert_manager import cert_manager
from magnum.common.x509 import operations as x509
from magnum.conductor.handlers.common import cert_manager as cert_manager_handlers
from oslo_config import cfg
from oslo_serialization import base64
from oslo_utils import encodeutils

from magnum_cluster_api import clients, helm, image_utils, images, objects, utils
from magnum_cluster_api.integrations import cinder, cloud_provider, manila

CONF = cfg.CONF
CALICO_TAG = "v3.24.2"

CLUSTER_CLASS_VERSION = pkg_resources.require("magnum_cluster_api")[0].version
CLUSTER_CLASS_NAME = f"magnum-v{CLUSTER_CLASS_VERSION}"
CLUSTER_CLASS_NODE_VOLUME_DETACH_TIMEOUT = "300s"  # seconds

CLUSTER_UPGRADE_LABELS = {"kube_tag"}

PLACEHOLDER = "PLACEHOLDER"

AUTOSCALE_ANNOTATION_MIN = "cluster.x-k8s.io/cluster-api-autoscaler-node-group-min-size"
AUTOSCALE_ANNOTATION_MAX = "cluster.x-k8s.io/cluster-api-autoscaler-node-group-max-size"


class ClusterAutoscalerHelmRelease:
    def __init__(self, api, cluster) -> None:
        self.cluster = cluster

    @property
    def apply(self):
        image = images.get_cluster_autoscaler_image(
            utils.get_kube_tag(self.cluster),
        )
        image_repo, image_tag = image.split(":", 1)

        return helm.UpgradeReleaseCommand(
            namespace="magnum-system",
            release_name=self.cluster.stack_id,
            chart_ref=os.path.join(
                pkg_resources.resource_filename("magnum_cluster_api", "charts"),
                "cluster-autoscaler/",
            ),
            values={
                "fullnameOverride": f"{self.cluster.stack_id}-autoscaler",
                "cloudProvider": "clusterapi",
                "clusterAPIMode": "kubeconfig-incluster",
                "clusterAPIKubeconfigSecret": f"{self.cluster.stack_id}-kubeconfig",
                "autoDiscovery": {
                    "clusterName": self.cluster.stack_id,
                },
                "image": {
                    "repository": image_repo,
                    "tag": image_tag,
                },
                "nodeSelector": {
                    "openstack-control-plane": "enabled",
                },
            },
        )

    @property
    def delete(self):
        return helm.DeleteReleaseCommand(
            namespace="magnum-system",
            release_name=self.cluster.stack_id,
            skip_missing=True,
        )


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
    def __init__(self, api: pykube.HTTPClient, cluster: magnum_objects.Cluster):
        super().__init__(api)
        self.cluster = cluster

    @property
    def labels(self) -> dict:
        return {
            "cluster-uuid": self.cluster.uuid,
        }


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

        repository = utils.get_cluster_container_infra_prefix(self.cluster)

        osc = clients.get_openstack_api(self.context)

        data = {
            **{
                os.path.basename(manifest): image_utils.update_manifest_images(
                    self.cluster.uuid,
                    manifest,
                    repository=repository,
                    replacements=[
                        (
                            "docker.io/k8scloudprovider/openstack-cloud-controller-manager:latest",
                            cloud_provider.get_image(self.cluster),
                        ),
                    ],
                )
                for manifest in glob.glob(os.path.join(manifests_path, "ccm/*.yaml"))
            },
            **{
                "calico.yml": image_utils.update_manifest_images(
                    self.cluster.uuid,
                    os.path.join(manifests_path, f"calico/{calico_version}.yaml"),
                    repository=repository,
                )
            },
        }

        if cinder.is_enabled(self.cluster):
            volume_types = osc.cinder().volume_types.list()
            default_volume_type = osc.cinder().volume_types.default()
            data = {
                **data,
                **{
                    os.path.basename(manifest): image_utils.update_manifest_images(
                        self.cluster.uuid,
                        manifest,
                        repository=repository,
                        replacements=[
                            (
                                "docker.io/k8scloudprovider/cinder-csi-plugin:latest",
                                cinder.get_image(self.cluster),
                            ),
                        ],
                    )
                    for manifest in glob.glob(
                        os.path.join(manifests_path, "cinder-csi/*.yaml")
                    )
                },
                **{
                    f"storageclass-block-{vt.name}.yaml": yaml.dump(
                        {
                            "apiVersion": objects.StorageClass.version,
                            "allowVolumeExpansion": True,
                            "kind": objects.StorageClass.kind,
                            "metadata": {
                                "annotations": (
                                    {
                                        "storageclass.kubernetes.io/is-default-class": "true"
                                    }
                                    if default_volume_type.name == vt.name
                                    else {}
                                ),
                                "name": "block-%s" % utils.convert_to_rfc1123(vt.name),
                            },
                            "provisioner": "cinder.csi.openstack.org",
                            "parameters": {
                                "type": utils.convert_to_rfc1123(vt.name),
                            },
                            "reclaimPolicy": "Delete",
                            "volumeBindingMode": "Immediate",
                        }
                    )
                    for vt in volume_types
                    if vt.name != "__DEFAULT__"
                },
            }

        if manila.is_enabled(self.cluster):
            share_types = osc.manila().share_types.list()
            share_network_id = utils.get_cluster_label(
                self.cluster, "manila_csi_share_network_id", None
            )
            data = {
                **data,
                **{
                    "manila-csi-secret.yaml": yaml.dump(
                        {
                            "apiVersion": pykube.Secret.version,
                            "kind": pykube.Secret.kind,
                            "metadata": {
                                "name": "csi-manila-secrets",
                                "namespace": "kube-system",
                            },
                            "stringData": utils.generate_manila_csi_cloud_config(
                                self.context,
                                self.api,
                                self.cluster,
                            ),
                        },
                    )
                },
                **{
                    os.path.basename(manifest): image_utils.update_manifest_images(
                        self.cluster.uuid,
                        manifest,
                        repository=repository,
                    )
                    for manifest in glob.glob(
                        os.path.join(manifests_path, "nfs-csi/*.yaml")
                    )
                },
                **{
                    os.path.basename(manifest): image_utils.update_manifest_images(
                        self.cluster.uuid,
                        manifest,
                        repository=repository,
                        replacements=[
                            (
                                "registry.k8s.io/provider-os/manila-csi-plugin:latest",
                                manila.get_image(self.cluster),
                            ),
                        ],
                    )
                    for manifest in glob.glob(
                        os.path.join(manifests_path, "manila-csi/*.yaml")
                    )
                },
            }
            # NOTE: We only create StorageClasses if share_network_id specified.
            if share_network_id:
                data = {
                    **data,
                    **{
                        f"storageclass-share-{st.name}.yaml": yaml.dump(
                            {
                                "apiVersion": objects.StorageClass.version,
                                "allowVolumeExpansion": True,
                                "kind": objects.StorageClass.kind,
                                "metadata": {
                                    "name": "share-%s"
                                    % utils.convert_to_rfc1123(st.name),
                                },
                                "provisioner": "manila.csi.openstack.org",
                                "parameters": {
                                    "type": st.name,
                                    "shareNetworkID": share_network_id,
                                    "csi.storage.k8s.io/provisioner-secret-name": "csi-manila-secrets",
                                    "csi.storage.k8s.io/provisioner-secret-namespace": "kube-system",
                                    "csi.storage.k8s.io/controller-expand-secret-name": "csi-manila-secrets",
                                    "csi.storage.k8s.io/controller-expand-secret-namespace": "kube-system",
                                    "csi.storage.k8s.io/node-stage-secret-name": "csi-manila-secrets",
                                    "csi.storage.k8s.io/node-stage-secret-namespace": "kube-system",
                                    "csi.storage.k8s.io/node-publish-secret-name": "csi-manila-secrets",
                                    "csi.storage.k8s.io/node-publish-secret-namespace": "kube-system",
                                },
                                "reclaimPolicy": "Delete",
                                "volumeBindingMode": "Immediate",
                            }
                        )
                        for st in share_types
                    },
                }

        if utils.get_cluster_label_as_bool(self.cluster, "keystone_auth_enabled", True):
            auth_url = osc.url_for(
                service_type="identity",
                interface=CONF.capi_client.endpoint_type.replace("URL", ""),
            )
            data = {
                **data,
                **{
                    "keystone-auth.yaml": helm.TemplateReleaseCommand(
                        namespace="kube-system",
                        release_name="k8s-keystone-auth",
                        chart_ref=os.path.join(
                            pkg_resources.resource_filename(
                                "magnum_cluster_api", "charts"
                            ),
                            "k8s-keystone-auth/",
                        ),
                        values={
                            "conf": {
                                "auth_url": auth_url
                                + ("" if auth_url.endswith("/v3") else "/v3"),
                                "ca_file": utils.get_cloud_ca_cert(),
                                "policy": utils.get_keystone_auth_default_policy(
                                    self.cluster
                                ),
                            },
                        },
                    )(repository=repository)
                },
            }

        return pykube.ConfigMap(
            self.api,
            {
                "apiVersion": pykube.ConfigMap.version,
                "kind": pykube.ConfigMap.kind,
                "metadata": {
                    "name": self.cluster.uuid,
                    "namespace": "magnum-system",
                },
                "data": data,
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
    def __init__(
        self, context: context.RequestContext, api: pykube.HTTPClient, cluster: any
    ):
        super().__init__(api, cluster)
        self.context = context

    def delete(self) -> None:
        resource = self.get_or_none()
        if resource:
            resource.delete()

    def get_or_none(self) -> pykube.Secret:
        return pykube.Secret.objects(self.api, namespace="magnum-system").get_or_none(
            name=f"{self.cluster.stack_id}-{self.CERT}"
        )

    def get_certificate(self) -> cert_manager.Cert:
        raise NotImplementedError()

    def get_object(self) -> pykube.Secret:
        cert_ref = getattr(self.cluster, self.REF)
        if cert_ref is None:
            raise Exception("Certificate for %s doesn't exist." % self.REF)
        ca_cert = self.get_certificate()

        return pykube.Secret(
            self.api,
            {
                "apiVersion": pykube.Secret.version,
                "kind": pykube.Secret.kind,
                "type": "cluster.x-k8s.io/secret",
                "metadata": {
                    "name": f"{self.cluster.stack_id}-{self.CERT}",
                    "namespace": "magnum-system",
                    "labels": {
                        "cluster.x-k8s.io/cluster-name": f"{self.cluster.stack_id}",
                    },
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

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_ca_certificate(
            self.cluster, self.context, "kubernetes"
        )


class EtcdCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "etcd"
    REF = "etcd_ca_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_ca_certificate(
            self.cluster, self.context, "etcd"
        )


class FrontProxyCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "proxy"
    REF = "front_proxy_ca_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_ca_certificate(
            self.cluster, self.context, "front-proxy"
        )


class ServiceAccountCertificateAuthoritySecret(CertificateAuthoritySecret):
    CERT = "sa"
    REF = "magnum_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_magnum_cert(self.cluster, self.context)


class CloudConfigSecret(ClusterBase):
    def __init__(
        self,
        context: context.RequestContext,
        api: pykube.HTTPClient,
        cluster: any,
        region_name: str = None,
        credential: any = types.SimpleNamespace(id=None, secret=None),
    ):
        super().__init__(api, cluster)
        self.context = context
        osc = clients.get_openstack_api(self.context)
        self.auth_url = osc.url_for(
            service_type="identity",
            interface=CONF.capi_client.endpoint_type.replace("URL", ""),
        )
        self.region_name = region_name
        self.credential = credential

    def get_object(self) -> pykube.Secret:
        ca_certificate = utils.get_capi_client_ca_cert()

        return pykube.Secret(
            self.api,
            {
                "apiVersion": pykube.Secret.version,
                "kind": pykube.Secret.kind,
                "metadata": {
                    "name": utils.get_cluster_api_cloud_config_secret_name(
                        self.cluster
                    ),
                    "namespace": "magnum-system",
                    "labels": self.labels,
                },
                "stringData": {
                    "cacert": (
                        ca_certificate
                        if ca_certificate
                        else open(certifi.where(), "r").read()
                    ),
                    "clouds.yaml": yaml.dump(
                        {
                            "clouds": {
                                "default": {
                                    "region_name": self.region_name,
                                    "endpoint_type": CONF.capi_client.endpoint_type.replace(
                                        "URL", ""
                                    ),
                                    "identity_api_version": 3,
                                    "verify": not CONF.capi_client.insecure,
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
            "magnum_cluster_api", "manifests"
        )
        audit_policy = open(os.path.join(manifests_path, "audit/policy.yaml")).read()
        keystone_auth_webhook = open(
            os.path.join(manifests_path, "keystone-auth/webhook.yaml")
        ).read()

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
                                        "extraVolumes": [
                                            # Note(oleks): Add this as default as a workaround of the json patch limitation # noqa: E501
                                            # https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass#json-patches-tips--tricks
                                            {
                                                "name": "webhooks",
                                                "hostPath": "/etc/kubernetes/webhooks",
                                                "mountPath": "/etc/kubernetes/webhooks",
                                            }
                                        ],
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
                                    {
                                        "path": "/etc/kubernetes/webhooks/webhookconfig.yaml",
                                        "owner": "root:root",
                                        "permissions": "0644",
                                        "content": base64.encode_as_text(
                                            keystone_auth_webhook
                                        ),
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
                                "preKubeadmCommands": [
                                    "rm /var/lib/etcd/lost+found -rf"
                                ],
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
                            "files": [
                                {
                                    "path": "/etc/kubernetes/.placeholder",
                                    "permissions": "0644",
                                    "content": base64.encode_as_text(PLACEHOLDER),
                                    "encoding": "base64",
                                },
                            ],
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
                        "spec": {
                            "cloudName": "default",
                            "flavor": PLACEHOLDER,
                        }
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
                            "allowAllInClusterTraffic": True,
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
                        "nodeVolumeDetachTimeout": CLUSTER_CLASS_NODE_VOLUME_DETACH_TIMEOUT,
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
                            "maxUnhealthy": "80%",
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
                                "nodeVolumeDetachTimeout": CLUSTER_CLASS_NODE_VOLUME_DETACH_TIMEOUT,
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
                                    "maxUnhealthy": "80%",
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
                            "name": "apiServerTLSCipherSuites",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "openidConnect",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "object",
                                    "required": [
                                        "issuerUrl",
                                        "clientId",
                                        "usernameClaim",
                                        "usernamePrefix",
                                        "groupsClaim",
                                        "groupsPrefix",
                                    ],
                                    "properties": {
                                        "issuerUrl": {
                                            "type": "string",
                                        },
                                        "clientId": {
                                            "type": "string",
                                        },
                                        "usernameClaim": {
                                            "type": "string",
                                        },
                                        "usernamePrefix": {
                                            "type": "string",
                                        },
                                        "groupsClaim": {
                                            "type": "string",
                                        },
                                        "groupsPrefix": {
                                            "type": "string",
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
                            "name": "cloudCaCert",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
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
                            "name": "systemdProxyConfig",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "aptProxyConfig",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "containerdConfig",
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
                            "name": "disableAPIServerFloatingIP",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "boolean",
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
                            "name": "fixedNetworkName",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "fixedSubnetId",
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
                            "name": "kubeletTLSCipherSuites",
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
                        {
                            "name": "operatingSystem",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                    "enum": utils.AVAILABLE_OPERATING_SYSTEMS,
                                    "default": "ubuntu",
                                },
                            },
                        },
                        {
                            "name": "enableEtcdVolume",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "boolean",
                                },
                            },
                        },
                        {
                            "name": "etcdVolumeSize",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "integer",
                                },
                            },
                        },
                        {
                            "name": "etcdVolumeType",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "availabilityZone",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "string",
                                },
                            },
                        },
                        {
                            "name": "enableKeystoneAuth",
                            "required": True,
                            "schema": {
                                "openAPIV3Schema": {
                                    "type": "boolean",
                                    "default": False,
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraVolumes/-",  # noqa: E501
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    name: audit-policy
                                                    hostPath: /etc/kubernetes/audit-policy
                                                    mountPath: /etc/kubernetes/audit-policy
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraVolumes/-",  # noqa: E501
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    name: audit-logs
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
                            "name": "openidConnect",
                            "enabledIf": "{{ if .openidConnect.issuerUrl }}true{{end}}",
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-issuer-url",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "openidConnect.issuerUrl",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-client-id",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "openidConnect.clientId",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-username-claim",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "openidConnect.usernameClaim",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-username-prefix",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "openidConnect.usernamePrefix",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-groups-claim",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "openidConnect.groupsClaim",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/oidc-groups-prefix",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "openidConnect.groupsPrefix",
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
                            "name": "ubuntu",
                            "enabledIf": '{{ if eq .operatingSystem "ubuntu" }}true{{end}}',
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/apt/apt.conf.d/90proxy"
                                                    owner: "root:root"
                                                    permissions: "0644"
                                                    content: "{{ .aptProxyConfig }}"
                                                    encoding: "base64"
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/preKubeadmCommands",
                                            "value": [
                                                "systemctl daemon-reload",
                                                "systemctl restart containerd",
                                            ],
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
                                            "path": "/spec/template/spec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/apt/apt.conf.d/90proxy"
                                                    owner: "root:root"
                                                    permissions: "0644"
                                                    content: "{{ .aptProxyConfig }}"
                                                    encoding: "base64"
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/preKubeadmCommands",
                                            "value": [
                                                "systemctl daemon-reload",
                                                "systemctl restart containerd",
                                            ],
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "flatcar",
                            "enabledIf": '{{ if eq .operatingSystem "flatcar" }}true{{end}}',
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/preKubeadmCommands/-",
                                            "value": textwrap.dedent(
                                                """\
                                            bash -c "sed -i 's/__REPLACE_NODE_NAME__/$(hostname -s)/g' /etc/kubeadm.yml"
                                            bash -c "test -f /tmp/containerd-bootstrap || (touch /tmp/containerd-bootstrap && systemctl daemon-reload && systemctl restart containerd)"
                                            """  # noqa: E501
                                            ),
                                        },
                                        {
                                            "op": "replace",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/format",
                                            "value": "ignition",
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/ignition",
                                            "value": {
                                                "containerLinuxConfig": {
                                                    "additionalConfig": textwrap.dedent(
                                                        """\
                                                        systemd:
                                                          units:
                                                          - name: coreos-metadata-sshkeys@.service
                                                            enabled: true
                                                          - name: kubeadm.service
                                                            enabled: true
                                                            dropins:
                                                            - name: 10-flatcar.conf
                                                              contents: |
                                                                [Unit]
                                                                Requires=containerd.service coreos-metadata.service
                                                                After=containerd.service coreos-metadata.service
                                                                [Service]
                                                                EnvironmentFile=/run/metadata/flatcar
                                                        """  # noqa: E501
                                                    ),
                                                },
                                            },
                                        },
                                        {
                                            "op": "replace",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/initConfiguration/nodeRegistration/name",  # noqa: E501
                                            "value": "__REPLACE_NODE_NAME__",
                                        },
                                        {
                                            "op": "replace",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/nodeRegistration/name",  # noqa: E501
                                            "value": "__REPLACE_NODE_NAME__",
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
                                            "path": "/spec/template/spec/preKubeadmCommands",
                                            "value": [
                                                textwrap.dedent(
                                                    """\
                                                bash -c "sed -i 's/__REPLACE_NODE_NAME__/$(hostname -s)/g' /etc/kubeadm.yml"
                                                bash -c "test -f /tmp/containerd-bootstrap || (touch /tmp/containerd-bootstrap && systemctl daemon-reload && systemctl restart containerd)"
                                                """  # noqa: E501
                                                )
                                            ],
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/format",
                                            "value": "ignition",
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/ignition",
                                            "value": {
                                                "containerLinuxConfig": {
                                                    "additionalConfig": textwrap.dedent(
                                                        """\
                                                        systemd:
                                                          units:
                                                          - name: coreos-metadata-sshkeys@.service
                                                            enabled: true
                                                          - name: kubeadm.service
                                                            enabled: true
                                                            dropins:
                                                            - name: 10-flatcar.conf
                                                              contents: |
                                                                [Unit]
                                                                Requires=containerd.service coreos-metadata.service
                                                                After=containerd.service coreos-metadata.service
                                                                [Service]
                                                                EnvironmentFile=/run/metadata/flatcar
                                                        """  # noqa: E501
                                                    ),
                                                },
                                            },
                                        },
                                        {
                                            "op": "replace",
                                            "path": "/spec/template/spec/joinConfiguration/nodeRegistration/name",
                                            "value": "__REPLACE_NODE_NAME__",
                                        },
                                    ],
                                },
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
                                            "path": "/spec/template/spec/disableAPIServerFloatingIP",
                                            "valueFrom": {
                                                "variable": "disableAPIServerFloatingIP"
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
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "controlPlaneAvailabilityZone",
                            "enabledIf": '{{ if ne .availabilityZone "" }}true{{end}}',
                            "definitions": [
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
                                            "path": "/spec/template/spec/controlPlaneAvailabilityZones",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    - "{{ .availabilityZone }}"
                                                    """
                                                ),
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "newNetworkConfig",
                            "enabledIf": '{{ if eq .fixedNetworkName "" }}true{{end}}',
                            "definitions": [
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
                                            "path": "/spec/template/spec/nodeCidr",
                                            "valueFrom": {"variable": "nodeCidr"},
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "existingFixedNetworkNameConfig",
                            "enabledIf": '{{ if ne .fixedNetworkName "" }}true{{end}}',
                            "definitions": [
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
                                            "path": "/spec/template/spec/network/name",
                                            "valueFrom": {
                                                "variable": "fixedNetworkName"
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "existingFixedSubnetIdConfig",
                            "enabledIf": '{{ if ne .fixedSubnetId "" }}true{{end}}',
                            "definitions": [
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
                                            "path": "/spec/template/spec/subnet/id",
                                            "valueFrom": {"variable": "fixedSubnetId"},
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "customImageRepository",
                            "enabledIf": '{{ if ne .imageRepository "" }}true{{end}}',
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
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "etcdVolume",
                            "enabledIf": "{{ if .enableEtcdVolume }}true{{end}}",
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/diskSetup",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    "partitions":
                                                      - "device": "/dev/vdb"
                                                        "tableType": "gpt"
                                                        "layout": True
                                                        "overwrite": False
                                                    "filesystems":
                                                      - "label": "etcd_disk"
                                                        "filesystem": "ext4"
                                                        "device": "/dev/vdb"
                                                        "extraOpts": ["-F", "-E", "lazy_itable_init=1,lazy_journal_init=1"] # noqa: E501
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/mounts",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    - - LABEL=etcd_disk
                                                      - /var/lib/etcd
                                                    """
                                                ),
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
                                        },
                                    },
                                    "jsonPatches": [
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/additionalBlockDevices",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    - name: etcd
                                                      sizeGiB: {{ .etcdVolumeSize }}
                                                      storage:
                                                        type: Volume
                                                        volume:
                                                          type: "{{ .etcdVolumeType }}"
                                                          availabilityZone: "{{ .availabilityZone }}"
                                                    """
                                                ),
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "keystoneAuth",
                            "enabledIf": "{{ if .enableKeystoneAuth }}true{{end}}",
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/authentication-token-webhook-config-file",  # noqa: E501
                                            "value": "/etc/kubernetes/webhooks/webhookconfig.yaml",
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/authorization-webhook-config-file",  # noqa: E501
                                            "value": "/etc/kubernetes/webhooks/webhookconfig.yaml",
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/authorization-mode",  # noqa: E501
                                            "value": "Node,RBAC,Webhook",
                                        },
                                    ],
                                }
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
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/extraArgs/tls-cipher-suites",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "apiServerTLSCipherSuites",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/initConfiguration/nodeRegistration/kubeletExtraArgs/tls-cipher-suites",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "kubeletTLSCipherSuites",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/joinConfiguration/nodeRegistration/kubeletExtraArgs/tls-cipher-suites",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "kubeletTLSCipherSuites",
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/clusterConfiguration/apiServer/certSANs",  # noqa: E501
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    - {{ .builtin.cluster.name }}
                                                    - {{ .builtin.cluster.name }}.{{ .builtin.cluster.namespace }}
                                                    - {{ .builtin.cluster.name }}.{{ .builtin.cluster.namespace }}.svc
                                                    - {{ .builtin.cluster.name }}.{{ .builtin.cluster.namespace }}.svc.cluster.local # noqa: E501
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/containerd/config.toml"
                                                    owner: "root:root"
                                                    permissions: "0644"
                                                    content: "{{ .containerdConfig }}"
                                                    encoding: "base64"
                                                    """
                                                )
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
                                                )
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/kubernetes/cloud_ca.crt"
                                                    owner: "root:root"
                                                    permissions: "0600"
                                                    content: "{{ .cloudCaCert }}"
                                                    encoding: "base64"
                                                    """
                                                )
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/kubeadmConfigSpec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/systemd/system/containerd.service.d/proxy.conf"
                                                    owner: "root:root"
                                                    permissions: "0644"
                                                    content: "{{ .systemdProxyConfig }}"
                                                    encoding: "base64"
                                                    """
                                                )
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
                                            "path": "/spec/template/spec/files/-",
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
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/kubernetes/cloud_ca.crt"
                                                    owner: "root:root"
                                                    permissions: "0600"
                                                    content: "{{ .cloudCaCert }}"
                                                    encoding: "base64"
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/containerd/config.toml"
                                                    owner: "root:root"
                                                    permissions: "0644"
                                                    content: "{{ .containerdConfig }}"
                                                    encoding: "base64"
                                                    """
                                                ),
                                            },
                                        },
                                        {
                                            "op": "add",
                                            "path": "/spec/template/spec/files/-",
                                            "valueFrom": {
                                                "template": textwrap.dedent(
                                                    """\
                                                    path: "/etc/systemd/system/containerd.service.d/proxy.conf"
                                                    owner: "root:root"
                                                    permissions: "0644"
                                                    content: "{{ .systemdProxyConfig }}"
                                                    encoding: "base64"
                                                    """
                                                ),
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "name": "workerConfig",
                            "definitions": [
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
                                            "path": "/spec/template/spec/joinConfiguration/nodeRegistration/kubeletExtraArgs/tls-cipher-suites",  # noqa: E501
                                            "valueFrom": {
                                                "variable": "kubeletTLSCipherSuites",
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


def mutate_machine_deployment(
    context: context.RequestContext,
    cluster: objects.Cluster,
    node_group: magnum_objects.NodeGroup,
    machine_deployment: dict = {},
):
    """
    This function will either makes updates to machine deployment fields which
    will not cause a rolling update or will return a new machine deployment
    if none is provided.
    """

    auto_scaling_enabled = utils.get_auto_scaling_enabled(cluster)

    machine_deployment.setdefault(
        "metadata",
        {
            "annotations": {},
            "labels": {},
        },
    )

    # Node labels
    machine_deployment["metadata"]["labels"] = {
        f"node-role.kubernetes.io/{node_group.role}": "",
        "node.cluster.x-k8s.io/nodegroup": node_group.name,
    }

    # Replicas (or min/max if auto-scaling is enabled)
    if auto_scaling_enabled:
        machine_deployment["replicas"] = None
        machine_deployment["metadata"]["annotations"] = {
            AUTOSCALE_ANNOTATION_MIN: str(
                utils.get_node_group_min_node_count(node_group)
            ),
            AUTOSCALE_ANNOTATION_MAX: str(
                utils.get_node_group_max_node_count(context, node_group)
            ),
        }
    else:
        machine_deployment["replicas"] = node_group.node_count
        machine_deployment["metadata"]["annotations"] = {}

    # Fixes
    machine_deployment["nodeVolumeDetachTimeout"] = (
        CLUSTER_CLASS_NODE_VOLUME_DETACH_TIMEOUT
    )

    # Anything beyond this point will *NOT* be changed in the machine deployment
    # for update operations (i.e. if the machine deployment already exists).
    if machine_deployment.get("name") == node_group.name:
        return machine_deployment

    # At this point, this is all code that will be added for brand new machine
    # deployments.  We can bring any of this code into the above block if we
    # want to change it for existing machine deployments.
    machine_deployment.update(
        {
            "class": "default-worker",
            "name": node_group.name,
            "failureDomain": utils.get_node_group_label(
                context, node_group, "availability_zone", ""
            ),
            "machineHealthCheck": {
                "enable": utils.get_cluster_label_as_bool(
                    cluster, "auto_healing_enabled", True
                )
            },
            "variables": {
                "overrides": [
                    {
                        "name": "bootVolume",
                        "value": {
                            "size": utils.get_node_group_label_as_int(
                                context,
                                node_group,
                                "boot_volume_size",
                                CONF.cinder.default_boot_volume_size,
                            ),
                            "type": utils.get_node_group_label(
                                context,
                                node_group,
                                "boot_volume_type",
                                cinder.get_default_boot_volume_type(context),
                            ),
                        },
                    },
                    {
                        "name": "flavor",
                        "value": node_group.flavor_id,
                    },
                    {
                        "name": "imageRepository",
                        "value": utils.get_node_group_label(
                            context,
                            node_group,
                            "container_infra_prefix",
                            "",
                        ),
                    },
                    {
                        "name": "imageUUID",
                        "value": utils.get_image_uuid(node_group.image_id, context),
                    },
                ],
            },
        }
    )

    return machine_deployment


def generate_machine_deployments_for_cluster(
    context: context.RequestContext, cluster: objects.Cluster
) -> list:
    machine_deployments = []
    for ng in cluster.nodegroups:
        if ng.role == "master" or ng.status.startswith("DELETE"):
            continue

        machine_deployment = mutate_machine_deployment(context, cluster, ng)
        machine_deployments.append(machine_deployment)

    return machine_deployments


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
        cni_version = utils.get_cluster_label(self.cluster, "calico_tag", CALICO_TAG)
        labels = {
            "cni": f"calico-{cni_version}",
        }

        return {**super().labels, **labels}

    def get_or_none(self) -> objects.Cluster:
        return objects.Cluster.objects(self.api, namespace="magnum-system").get_or_none(
            name=self.cluster.stack_id
        )

    def get_observed_generation(self) -> int:
        capi_cluster = self.get_or_none()
        if capi_cluster:
            return capi_cluster.obj["status"]["observedGeneration"]
        raise Exception("Cluster doesn't exists.")

    def get_object(self) -> objects.Cluster:
        osc = clients.get_openstack_api(self.context)
        default_volume_type = osc.cinder().volume_types.default()
        return objects.Cluster(
            self.api,
            {
                "apiVersion": objects.Cluster.version,
                "kind": objects.Cluster.kind,
                "metadata": {
                    "name": self.cluster.stack_id,
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
                        "services": {
                            "cidrBlocks": [
                                utils.get_cluster_label(
                                    self.cluster,
                                    "service_cluster_ip_range",
                                    "10.254.0.0/16",
                                )
                            ],
                        },
                    },
                    "topology": {
                        "class": CLUSTER_CLASS_NAME,
                        "version": utils.get_kube_tag(self.cluster),
                        "controlPlane": {
                            "metadata": {
                                "labels": {
                                    "node-role.kubernetes.io/master": "",
                                }
                            },
                            "replicas": self.cluster.master_count,
                            "machineHealthCheck": {
                                "enable": utils.get_cluster_label_as_bool(
                                    self.cluster, "auto_healing_enabled", True
                                )
                            },
                        },
                        "workers": {
                            "machineDeployments": generate_machine_deployments_for_cluster(
                                self.context, self.cluster
                            ),
                        },
                        "variables": [
                            {
                                "name": "apiServerLoadBalancer",
                                "value": {
                                    "enabled": self.cluster.master_lb_enabled,
                                },
                            },
                            {
                                "name": "apiServerTLSCipherSuites",
                                "value": utils.get_cluster_label(
                                    self.cluster,
                                    "api_server_tls_cipher_suites",
                                    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305",  # noqa: E501
                                ),
                            },
                            {
                                "name": "openidConnect",
                                "value": {
                                    "clientId": utils.get_cluster_label(
                                        self.cluster, "oidc_client_id", ""
                                    ),
                                    "groupsClaim": utils.get_cluster_label(
                                        self.cluster, "oidc_groups_claim", ""
                                    ),
                                    "groupsPrefix": utils.get_cluster_label(
                                        self.cluster, "oidc_groups_prefix", ""
                                    ),
                                    "issuerUrl": utils.get_cluster_label(
                                        self.cluster, "oidc_issuer_url", ""
                                    ),
                                    "usernameClaim": utils.get_cluster_label(
                                        self.cluster, "oidc_username_claim", "sub"
                                    ),
                                    "usernamePrefix": utils.get_cluster_label(
                                        self.cluster, "oidc_username_prefix", "-"
                                    ),
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
                                    "name": utils.get_cluster_api_cloud_config_secret_name(
                                        self.cluster
                                    ),
                                },
                            },
                            {
                                "name": "cloudCaCert",
                                "value": base64.encode_as_text(
                                    utils.get_cloud_ca_cert()
                                ),
                            },
                            {
                                "name": "cloudControllerManagerConfig",
                                "value": base64.encode_as_text(
                                    utils.generate_cloud_controller_manager_config(
                                        self.context, self.api, self.cluster
                                    )
                                ),
                            },
                            {
                                "name": "systemdProxyConfig",
                                "value": base64.encode_as_text(
                                    utils.generate_systemd_proxy_config(self.cluster)
                                ),
                            },
                            {
                                "name": "aptProxyConfig",
                                "value": base64.encode_as_text(
                                    utils.generate_apt_proxy_config(self.cluster)
                                ),
                            },
                            {
                                "name": "containerdConfig",
                                "value": base64.encode_as_text(
                                    utils.generate_containerd_config(self.cluster)
                                ),
                            },
                            {
                                "name": "controlPlaneFlavor",
                                "value": self.cluster.master_flavor_id,
                            },
                            {
                                "name": "disableAPIServerFloatingIP",
                                "value": utils.get_cluster_floating_ip_disabled(
                                    self.cluster
                                ),
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
                                "name": "fixedNetworkName",
                                "value": neutron.get_fixed_network_name(
                                    self.context, self.cluster.fixed_network
                                )
                                or "",
                            },
                            {
                                "name": "fixedSubnetId",
                                "value": neutron.get_fixed_subnet_id(
                                    self.context, self.cluster.fixed_subnet
                                )
                                or "",
                            },
                            {
                                "name": "flavor",
                                "value": self.cluster.flavor_id,
                            },
                            {
                                "name": "imageRepository",
                                "value": utils.get_cluster_container_infra_prefix(
                                    self.cluster,
                                ),
                            },
                            {
                                "name": "imageUUID",
                                "value": utils.get_image_uuid(
                                    self.cluster.default_ng_master.image_id,
                                    self.context,
                                ),
                            },
                            {
                                "name": "kubeletTLSCipherSuites",
                                "value": utils.get_cluster_label(
                                    self.cluster,
                                    "kubelet_tls_cipher_suites",
                                    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305",  # noqa: E501
                                ),
                            },
                            {
                                "name": "nodeCidr",
                                "value": utils.get_cluster_label(
                                    self.cluster,
                                    "fixed_subnet_cidr",
                                    "10.0.0.0/24",
                                ),
                            },
                            {
                                "name": "sshKeyName",
                                "value": self.cluster.keypair or "",
                            },
                            {
                                "name": "operatingSystem",
                                "value": utils.get_operating_system(self.cluster),
                            },
                            {
                                "name": "enableEtcdVolume",
                                "value": utils.get_cluster_label_as_int(
                                    self.cluster,
                                    "etcd_volume_size",
                                    0,
                                )
                                > 0,
                            },
                            {
                                "name": "etcdVolumeSize",
                                "value": utils.get_cluster_label_as_int(
                                    self.cluster,
                                    "etcd_volume_size",
                                    0,
                                ),
                            },
                            {
                                "name": "etcdVolumeType",
                                "value": utils.get_cluster_label(
                                    self.cluster,
                                    "etcd_volume_type",
                                    default_volume_type.name,
                                ),
                            },
                            {
                                "name": "availabilityZone",
                                "value": utils.get_cluster_label(
                                    self.cluster, "availability_zone", ""
                                ),
                            },
                            {
                                "name": "enableKeystoneAuth",
                                "value": utils.get_cluster_label_as_bool(
                                    self.cluster, "keystone_auth_enabled", True
                                ),
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


def apply_cluster_from_magnum_cluster(
    context: context.RequestContext,
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
    cluster_template: magnum_objects.ClusterTemplate = None,
    skip_auto_scaling_release: bool = False,
) -> None:
    """
    Create a ClusterAPI cluster given a Magnum Cluster object.
    """
    create_cluster_class(api)

    if cluster_template is None:
        cluster_template = cluster.cluster_template
        cluster.cluster_template_id = cluster_template.uuid

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

    if not skip_auto_scaling_release and utils.get_auto_scaling_enabled(cluster):
        ClusterAutoscalerHelmRelease(api, cluster).apply()


def get_kubeadm_control_plane(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> objects.KubeadmControlPlane:
    kcps = objects.KubeadmControlPlane.objects(api, namespace="magnum-system").filter(
        selector={
            "cluster.x-k8s.io/cluster-name": cluster.stack_id,
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
            "cluster.x-k8s.io/cluster-name": cluster.stack_id,
            "topology.cluster.x-k8s.io/deployment-name": node_group.name,
        },
    )
    if len(mds) == 1:
        return list(mds)[0]
    return None
