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

import abc
import glob
import math
import os
import types
import typing

import certifi
import pkg_resources
import pykube  # type: ignore
import yaml
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import context, neutron  # type: ignore
from magnum.common import utils as magnum_utils  # type: ignore
from magnum.common.cert_manager import cert_manager  # type: ignore
from magnum.common.x509 import operations as x509  # type: ignore
from magnum.conductor.handlers.common import (
    cert_manager as cert_manager_handlers,  # type: ignore
)
from oslo_config import cfg  # type: ignore
from oslo_serialization import base64  # type: ignore
from oslo_utils import encodeutils  # type: ignore

from magnum_cluster_api import (
    clients,
    helm,
    image_utils,
    images,
    magnum_cluster_api,
    objects,
    utils,
)
from magnum_cluster_api.integrations import cinder, manila

CONF = cfg.CONF
CALICO_TAG = "v3.29.2"

CLUSTER_CLASS_VERSION = pkg_resources.require("magnum_cluster_api")[0].version
CLUSTER_CLASS_NAME = f"magnum-v{CLUSTER_CLASS_VERSION}"
CLUSTER_CLASS_NODE_VOLUME_DETACH_TIMEOUT = "300s"  # seconds

AUTOSCALE_ANNOTATION_MIN = "cluster.x-k8s.io/cluster-api-autoscaler-node-group-min-size"
AUTOSCALE_ANNOTATION_MAX = "cluster.x-k8s.io/cluster-api-autoscaler-node-group-max-size"

DEFAULT_POD_CIDR = "10.100.0.0/16"


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
                "extraArgs": {
                    "logtostderr": True,
                    "stderrthreshold": "info",
                    "v": 4,
                    "enforce-node-group-min-size": True,
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


class ClusterServerGroups:
    def __init__(
        self, context: context.RequestContext, cluster: magnum_objects.Cluster
    ) -> None:
        self.cluster = cluster
        self.context = context
        self.osc = clients.get_openstack_api(self.context)

    def apply(self):
        # Create a server group for controlplane
        utils.ensure_controlplane_server_group(ctx=self.context, cluster=self.cluster)

        # Create a server group per a nodegroup
        for ng in self.cluster.nodegroups:
            if ng.role == "master":
                continue
            utils.ensure_worker_server_group(
                ctx=self.context, cluster=self.cluster, node_group=ng
            )

    def delete(self):
        # delete controlplane server group
        utils.delete_controlplane_server_group(ctx=self.context, cluster=self.cluster)

        # Create worker server groups
        for ng in self.cluster.nodegroups:
            if ng.role == "master":
                continue

            utils.delete_worker_server_group(
                ctx=self.context, cluster=self.cluster, node_group=ng
            )


class Base(abc.ABC):
    def __init__(self, api: magnum_cluster_api.KubeClient, namespace="magnum-system"):
        self.api = api
        self.namespace = namespace

    @property
    @abc.abstractmethod
    def api_version(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def kind(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    @abc.abstractmethod
    def get_object(self) -> dict:
        pass

    def get_resource(self) -> dict:
        resource = self.get_object()

        resource["apiVersion"] = self.api_version
        resource["kind"] = self.kind

        resource.setdefault("metadata", {})
        resource["metadata"].setdefault("name", self.name)
        if self.kind != "Namespace":
            resource["metadata"].setdefault("namespace", self.namespace)

        return resource

    def apply(self):
        resource = self.get_resource()
        self.api.create_or_update(resource)

    def delete(self) -> None:
        self.api.delete(
            self.api_version, self.kind, self.name, namespace=self.namespace
        )


class ClusterBase(Base):
    def __init__(
        self, api: magnum_cluster_api.KubeClient, cluster: magnum_objects.Cluster
    ):
        super().__init__(api)
        self.cluster = cluster

    @property
    def name(self) -> str:
        return self.cluster.uuid

    @property
    def labels(self) -> dict:
        return {
            "cluster-uuid": self.cluster.uuid,
        }


class ClusterResourcesSecret(ClusterBase):
    def __init__(
        self,
        context: context.RequestContext,
        api: magnum_cluster_api.KubeClient,
        pykube_api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
        namespace: str = "magnum-system",
    ):
        self.context = context
        self.api = api
        self.pykube_api = pykube_api
        self.cluster = cluster
        self.namespace = namespace

    @property
    def api_version(self) -> str:
        return "v1"

    @property
    def kind(self) -> str:
        return "Secret"

    def get_object(self) -> dict:
        repository = utils.get_cluster_container_infra_prefix(self.cluster)
        manifests_path = pkg_resources.resource_filename(
            "magnum_cluster_api", "manifests"
        )

        data = magnum_cluster_api.MagnumCluster.get_config_data(self.cluster)

        data = {
            **data,
            **{
                "cloud-config-secret.yaml": yaml.dump(
                    {
                        "apiVersion": pykube.Secret.version,
                        "kind": pykube.Secret.kind,
                        "metadata": {
                            "name": "cloud-config",
                            "namespace": "kube-system",
                        },
                        "stringData": {
                            "cloud.conf": utils.generate_cloud_controller_manager_config(
                                self.context,
                                self.pykube_api,
                                self.cluster,
                            ),
                            "ca.crt": magnum_utils.get_openstack_ca(),
                        },
                    }
                ),
            },
        }

        if self.cluster.cluster_template.network_driver == "calico":
            calico_version = self.cluster.labels.get("calico_tag", CALICO_TAG)
            data = {
                **data,
                **{
                    "calico.yml": image_utils.update_manifest_images(
                        self.cluster.uuid,
                        os.path.join(manifests_path, f"calico/{calico_version}.yaml"),
                        repository=repository,
                    )
                },
            }

        osc = clients.get_openstack_api(self.context)

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
                                "type": vt.name,
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
            share_network_id = self.cluster.labels.get("manila_csi_share_network_id")
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
                                self.pykube_api,
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
                interface="public",
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
                                "ca_cert": magnum_utils.get_openstack_ca(),
                                "policy": utils.get_keystone_auth_default_policy(
                                    self.cluster
                                ),
                            },
                        },
                    )(repository=repository)
                },
            }

        return {
            "type": "addons.cluster.x-k8s.io/resource-set",
            "stringData": data,
        }

    def get_or_none(self) -> objects.Cluster:
        return pykube.Secret.objects(
            self.pykube_api, namespace="magnum-system"
        ).get_or_none(name=self.name)

    def delete(self):
        cr_cm = self.get_or_none()
        if cr_cm:
            cr_cm.delete()


class CertificateAuthoritySecret(ClusterBase):
    def __init__(
        self,
        context: context.RequestContext,
        api: magnum_cluster_api.KubeClient,
        pykube_api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
    ):
        super().__init__(api, cluster)
        self.pykube_api = pykube_api
        self.context = context

    @abc.abstractmethod
    def certificate_name(self) -> str:
        pass

    @abc.abstractmethod
    def magnum_cert_ref_name(self) -> str:
        pass

    @property
    def api_version(self) -> str:
        return "v1"

    @property
    def kind(self) -> str:
        return "Secret"

    @property
    def name(self) -> str:
        return f"{self.cluster.stack_id}-{self.certificate_name()}"

    def delete(self) -> None:
        resource = self.get_or_none()
        if resource:
            resource.delete()

    def get_or_none(self) -> pykube.Secret:
        return pykube.Secret.objects(
            self.pykube_api, namespace="magnum-system"
        ).get_or_none(name=self.name)

    def get_certificate(self) -> cert_manager.Cert:
        raise NotImplementedError()

    def get_object(self) -> dict:
        cert_ref = getattr(self.cluster, self.magnum_cert_ref_name())
        if cert_ref is None:
            raise Exception(
                "Certificate for %s doesn't exist." % self.magnum_cert_ref_name()
            )
        ca_cert = self.get_certificate()

        return {
            "type": "cluster.x-k8s.io/secret",
            "metadata": {
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
        }


class ApiCertificateAuthoritySecret(CertificateAuthoritySecret):
    def certificate_name(self):
        return "ca"

    def magnum_cert_ref_name(self):
        return "ca_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_ca_certificate(
            self.cluster, self.context, "kubernetes"
        )


class EtcdCertificateAuthoritySecret(CertificateAuthoritySecret):
    def certificate_name(self):
        return "etcd"

    def magnum_cert_ref_name(self):
        return "etcd_ca_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_ca_certificate(
            self.cluster, self.context, "etcd"
        )


class FrontProxyCertificateAuthoritySecret(CertificateAuthoritySecret):
    def certificate_name(self):
        return "proxy"

    def magnum_cert_ref_name(self):
        return "front_proxy_ca_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_ca_certificate(
            self.cluster, self.context, "front-proxy"
        )


class ServiceAccountCertificateAuthoritySecret(CertificateAuthoritySecret):
    def certificate_name(self):
        return "sa"

    def magnum_cert_ref_name(self):
        return "magnum_cert_ref"

    def get_certificate(self) -> cert_manager.Cert:
        return cert_manager_handlers.get_cluster_magnum_cert(self.cluster, self.context)


class CloudConfigSecret(ClusterBase):
    def __init__(
        self,
        context: context.RequestContext,
        api: magnum_cluster_api.KubeClient,
        cluster: magnum_objects.Cluster,
        region_name: typing.Optional[str] = None,
        credential: types.SimpleNamespace = types.SimpleNamespace(id=None, secret=None),
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

    @property
    def api_version(self) -> str:
        return "v1"

    @property
    def kind(self) -> str:
        return "Secret"

    @property
    def name(self) -> str:
        return utils.get_cluster_api_cloud_config_secret_name(self.cluster)

    def get_object(self) -> dict:
        ca_certificate = utils.get_capi_client_ca_cert()

        return {
            "metadata": {
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
        }


def mutate_machine_deployment(
    context: context.RequestContext,
    cluster: objects.Cluster,
    node_group: magnum_objects.NodeGroup,
    machine_deployment: dict = None,
):
    """
    This function will either makes updates to machine deployment fields which
    will not cause a rolling update or will return a new machine deployment
    if none is provided.
    """

    # NOTE(okozachenko1203): Initialize as an empty dict if not provided
    #                        instead of using mutable default argument.
    if machine_deployment is None:
        machine_deployment = {}

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

    # Lookup the node group resources
    osc = clients.get_openstack_api(context)
    flavor = utils.lookup_flavor(osc, node_group.flavor_id)
    image = utils.lookup_image(osc, node_group.image_id)

    # Replicas (or min/max if auto-scaling is enabled)
    if auto_scaling_enabled:
        boot_volume_size = utils.get_node_group_label_as_int(
            node_group,
            "boot_volume_size",
            CONF.cinder.default_boot_volume_size,
        )
        if boot_volume_size == 0:
            boot_volume_size = flavor.disk

        machine_deployment["replicas"] = None
        machine_deployment["metadata"]["annotations"] = {
            AUTOSCALE_ANNOTATION_MIN: str(node_group.min_node_count),
            AUTOSCALE_ANNOTATION_MAX: str(
                utils.get_node_group_max_node_count(node_group)
            ),
            "capacity.cluster-autoscaler.kubernetes.io/memory": f"{math.ceil(flavor.ram / 1024)}G",
            "capacity.cluster-autoscaler.kubernetes.io/cpu": str(flavor.vcpus),
            "capacity.cluster-autoscaler.kubernetes.io/ephemeral-disk": str(
                boot_volume_size
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

    # At this point, this is all code that will be added for brand-new machine
    # deployments.  We can bring any of this code into the above block if we
    # want to change it for existing machine deployments.

    machine_deployment.update(
        {
            "class": "default-worker",
            "name": node_group.name,
            "failureDomain": node_group.labels.get("availability_zone", ""),
            "machineHealthCheck": {"enable": utils.get_auto_healing_enabled(cluster)},
            "variables": {
                "overrides": [
                    {
                        "name": "bootVolume",
                        "value": {
                            "size": utils.get_node_group_label_as_int(
                                node_group,
                                "boot_volume_size",
                                CONF.cinder.default_boot_volume_size,
                            ),
                            "type": node_group.labels.get(
                                "boot_volume_type",
                                cinder.get_default_boot_volume_type(context),
                            ),
                        },
                    },
                    {
                        "name": "flavor",
                        "value": flavor.name,
                    },
                    {
                        "name": "imageRepository",
                        "value": node_group.labels.get(
                            "container_infra_prefix",
                            "",
                        ),
                    },
                    {
                        "name": "imageUUID",
                        "value": image.get("id"),
                    },
                    {
                        "name": "hardwareDiskBus",
                        "value": image.get("hw_disk_bus", ""),
                    },
                    # NOTE(oleks): Override using MachineDeployment-level variables for node groups
                    {
                        "name": "serverGroupId",
                        "value": utils.ensure_worker_server_group(
                            ctx=context, cluster=cluster, node_group=node_group
                        ),
                    },
                    {
                        "name": "isServerGroupDiffFailureDomain",
                        "value": utils.is_node_group_different_failure_domain(
                            node_group=node_group, cluster=cluster
                        ),
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
        api: magnum_cluster_api.KubeClient,
        pykube_api: pykube.HTTPClient,
        cluster: magnum_objects.Cluster,
        namespace: str = "magnum-system",
    ):
        self.context = context
        self.api = api
        self.pykube_api = pykube_api
        self.cluster = cluster
        self.namespace = namespace

    @property
    def api_version(self) -> str:
        return "cluster.x-k8s.io/v1beta1"

    @property
    def kind(self) -> str:
        return "Cluster"

    @property
    def name(self) -> str:
        return self.cluster.stack_id

    @property
    def labels(self) -> dict:
        labels = {}
        if self.cluster.cluster_template.network_driver == "calico":
            cni_version = self.cluster.labels.get("calico_tag", CALICO_TAG)
            labels = {
                "cni": f"calico-{cni_version}",
            }

        return {**super().labels, **labels}

    def get_or_none(self) -> objects.Cluster:
        return objects.Cluster.objects(
            self.pykube_api, namespace=self.namespace
        ).get_or_none(name=self.cluster.stack_id)

    def get_object(self) -> dict:
        osc = clients.get_openstack_api(self.context)
        default_volume_type = osc.cinder().volume_types.default()
        pod_cidr = DEFAULT_POD_CIDR
        if self.cluster.cluster_template.network_driver == "calico":
            pod_cidr = self.cluster.labels.get(
                "calico_ipv4pool",
                DEFAULT_POD_CIDR,
            )
        if self.cluster.cluster_template.network_driver == "cilium":
            pod_cidr = self.cluster.labels.get(
                "cilium_ipv4pool",
                DEFAULT_POD_CIDR,
            )

        # Lookup the flavor from Nova
        control_plane_flavor = utils.lookup_flavor(osc, self.cluster.master_flavor_id)
        worker_flavor = utils.lookup_flavor(osc, self.cluster.flavor_id)
        image = utils.lookup_image(osc, self.cluster.default_ng_master.image_id)

        return {
            "metadata": {
                "labels": self.labels,
            },
            "spec": {
                "clusterNetwork": {
                    "serviceDomain": self.cluster.labels.get(
                        "dns_cluster_domain", "cluster.local"
                    ),
                    "pods": {
                        "cidrBlocks": [pod_cidr],
                    },
                    "services": {
                        "cidrBlocks": [
                            self.cluster.labels.get(
                                "service_cluster_ip_range", "10.254.0.0/16"
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
                            "enable": utils.get_auto_healing_enabled(self.cluster)
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
                                "provider": self.cluster.labels.get(
                                    "octavia_provider", "amphora"
                                ),
                            },
                        },
                        {
                            "name": "apiServerTLSCipherSuites",
                            "value": self.cluster.labels.get(
                                "api_server_tls_cipher_suites",
                                "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305",  # noqa: E501
                            ),
                        },
                        {
                            "name": "openidConnect",
                            "value": {
                                "clientId": self.cluster.labels.get(
                                    "oidc_client_id", ""
                                ),
                                "groupsClaim": self.cluster.labels.get(
                                    "oidc_groups_claim", ""
                                ),
                                "groupsPrefix": self.cluster.labels.get(
                                    "oidc_groups_prefix", ""
                                ),
                                "issuerUrl": self.cluster.labels.get(
                                    "oidc_issuer_url", ""
                                ),
                                "usernameClaim": self.cluster.labels.get(
                                    "oidc_username_claim", "sub"
                                ),
                                "usernamePrefix": self.cluster.labels.get(
                                    "oidc_username_prefix", "-"
                                ),
                            },
                        },
                        {
                            "name": "auditLog",
                            "value": {
                                "enabled": utils.get_cluster_label_as_bool(
                                    self.cluster, "audit_log_enabled", False
                                ),
                                "maxAge": self.cluster.labels.get(
                                    "audit_log_max_age", "30"
                                ),
                                "maxBackup": self.cluster.labels.get(
                                    "audit_log_max_backup", "10"
                                ),
                                "maxSize": self.cluster.labels.get(
                                    "audit_log_max_size", "100"
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
                                "type": self.cluster.labels.get(
                                    "boot_volume_type",
                                    cinder.get_default_boot_volume_type(self.context),
                                ),
                            },
                        },
                        {
                            "name": "clusterIdentityRefName",
                            "value": utils.get_cluster_api_cloud_config_secret_name(
                                self.cluster
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
                            "value": control_plane_flavor.name,
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
                            "name": "fixedNetworkId",
                            "value": utils.get_fixed_network_id(
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
                            "value": worker_flavor.name,
                        },
                        {
                            "name": "imageRepository",
                            "value": utils.get_cluster_container_infra_prefix(
                                self.cluster,
                            ),
                        },
                        {
                            "name": "imageUUID",
                            "value": image.get("id"),
                        },
                        {
                            "name": "kubeletTLSCipherSuites",
                            "value": self.cluster.labels.get(
                                "kubelet_tls_cipher_suites",
                                "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305",  # noqa: E501
                            ),
                        },
                        {
                            "name": "apiServerSANs",
                            "value": utils.generate_api_cert_san_list(self.cluster),
                        },
                        {
                            "name": "nodeCidr",
                            "value": self.cluster.labels.get(
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
                            "name": "hardwareDiskBus",
                            "value": image.get("hw_disk_bus", ""),
                        },
                        {
                            "name": "enableDockerVolume",
                            "value": self.cluster.docker_volume_size is not None,
                        },
                        {
                            "name": "dockerVolumeSize",
                            "value": self.cluster.docker_volume_size or 0,
                        },
                        {
                            "name": "dockerVolumeType",
                            "value": self.cluster.labels.get(
                                "docker_volume_type",
                                default_volume_type.name,
                            ),
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
                            "value": self.cluster.labels.get(
                                "etcd_volume_type",
                                default_volume_type.name,
                            ),
                        },
                        {
                            "name": "availabilityZone",
                            "value": self.cluster.labels.get("availability_zone", ""),
                        },
                        {
                            "name": "enableKeystoneAuth",
                            "value": utils.get_cluster_label_as_bool(
                                self.cluster, "keystone_auth_enabled", True
                            ),
                        },
                        {
                            "name": "controlPlaneAvailabilityZones",
                            "value": self.cluster.labels.get(
                                "control_plane_availability_zones", ""
                            ).split(","),
                        },
                        # NOTE(oleks): Set cluster-level variable using server group id for controlplane.
                        #              Override this for node groups via  MachineDeployment-level variable.
                        {
                            "name": "serverGroupId",
                            "value": utils.ensure_controlplane_server_group(
                                ctx=self.context, cluster=self.cluster
                            ),
                        },
                        # NOTE(oleks): Set cluster-level variable using cluster label for controlplane.
                        #              Override this using node group label for node groups via  MachineDeployment-level variable. # noqa: E501
                        {
                            "name": "isServerGroupDiffFailureDomain",
                            "value": utils.is_controlplane_different_failure_domain(
                                cluster=self.cluster
                            ),
                        },
                    ],
                },
            },
        }

    def delete(self):
        capi_cluster = self.get_or_none()
        if capi_cluster:
            capi_cluster.delete()


def apply_cluster_from_magnum_cluster(
    context: context.RequestContext,
    api: magnum_cluster_api.KubeClient,
    pykube_api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
    skip_auto_scaling_release: bool = False,
) -> None:
    """
    Create a ClusterAPI cluster given a Magnum Cluster object.
    """

    ClusterServerGroups(context, cluster).apply()
    ClusterResourcesSecret(context, api, pykube_api, cluster).apply()

    if not skip_auto_scaling_release and utils.get_auto_scaling_enabled(cluster):
        ClusterAutoscalerHelmRelease(api, cluster).apply()


def get_kubeadm_control_plane(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> typing.Optional[objects.KubeadmControlPlane]:
    kcps = objects.KubeadmControlPlane.objects(api, namespace="magnum-system").filter(
        selector={
            "cluster.x-k8s.io/cluster-name": cluster.stack_id,
        },
    )
    if len(kcps) == 1:
        return list(kcps)[0]
    return None
