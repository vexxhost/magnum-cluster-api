# Copyright 2022 VEXXHOST Inc. All rights reserved.
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

import os
import pykube
import pkg_resources
import glob

import textwrap
import yaml
import json

import oslo_serialization

import keystoneauth1

from magnum.common import clients
from magnum.drivers.common import driver
from magnum.common import neutron
from magnum import objects

from magnum_cluster_api import resources



class BaseDriver(driver.Driver):
    def create_cluster(self, context, cluster, cluster_create_timeout):
        osc = clients.OpenStackClients(context)
        k8s = pykube.HTTPClient(pykube.KubeConfig.from_env())

        resources.Namespace(k8s).apply()
        resources.CloudControllerManagerConfigMap(k8s, cluster).apply()
        resources.CloudControllerManagerClusterResourceSet(k8s, cluster).apply()

        if cluster.cluster_template.network_driver == "calico":
            resources.CalicoConfigMap(k8s, cluster).apply()
            resources.CalicoClusterResourceSet(k8s, cluster).apply()

        credential = osc.keystone().client.application_credentials.create(
            user=cluster.user_id,
            name=cluster.uuid,
            description=f"Magnum cluster ({cluster.uuid})",
        )

        resources.CloudConfigSecret(
            k8s, cluster, osc.auth_url, osc.cinder_region_name(), credential
        ).apply()

        for node_group in cluster.nodegroups:
            resources.OpenStackMachineTemplate(k8s, cluster, node_group).apply()
            if node_group.role == "master":
                resources.KubeadmControlPlane(
                    k8s,
                    cluster,
                    node_group,
                    auth_url=osc.auth_url,
                    region_name=osc.cinder_region_name(),
                    credential=credential,
                ).apply()
            else:
                resources.KubeadmConfigTemplate(k8s, cluster).apply()
                resources.MachineDeployment(k8s, cluster, node_group).apply()

        resources.OpenStackCluster(k8s, cluster, context).apply()
        resources.Cluster(k8s, cluster).apply()

    def update_cluster_status(self, context, cluster, use_admin_ctx=False):
        osc = clients.OpenStackClients(context)
        k8s = pykube.HTTPClient(pykube.KubeConfig.from_env())

        if cluster.status == objects.fields.ClusterStatus.DELETE_IN_PROGRESS:
            capi_cluster = resources.Cluster(k8s, cluster).get_object()
            if capi_cluster.exists():
                return

            # NOTE(mnaser): We delete the application credentials at this stage
            #               to make sure CAPI doesn't lose access to OpenStack.
            try:
                osc.keystone().client.application_credentials.find(
                    name=cluster.uuid,
                    user=cluster.user_id,
                ).delete()
            except keystoneauth1.exceptions.http.NotFound:
                pass
            resources.CloudConfigSecret(k8s, cluster).delete()

            cluster.status = objects.fields.ClusterStatus.DELETE_COMPLETE
            cluster.save()

    def update_cluster(self, context, cluster, scale_manager=None, rollback=False):
        raise NotImplementedError("Subclasses must implement " "'update_cluster'.")

    def resize_cluster(
        self,
        context,
        cluster,
        resize_manager,
        node_count,
        nodes_to_remove,
        nodegroup=None,
    ):
        raise NotImplementedError("Subclasses must implement " "'resize_cluster'.")

    def upgrade_cluster(
        self,
        context,
        cluster,
        cluster_template,
        max_batch_size,
        nodegroup,
        scale_manager=None,
        rollback=False,
    ):
        raise NotImplementedError("Subclasses must implement " "'upgrade_cluster'.")

    def delete_cluster(self, context, cluster):
        osc = clients.OpenStackClients(context)
        k8s = pykube.HTTPClient(pykube.KubeConfig.from_env())

        resources.Cluster(k8s, cluster).delete()
        resources.OpenStackCluster(k8s, cluster, context).delete()

        for node_group in cluster.nodegroups:
            resources.OpenStackMachineTemplate(k8s, cluster, node_group).delete()
            if node_group.role == "master":
                resources.KubeadmControlPlane(k8s, cluster, node_group).delete()
            else:
                resources.MachineDeployment(k8s, cluster, node_group).delete()
                resources.KubeadmConfigTemplate(k8s, cluster).delete()

    def create_federation(self, context, federation):
        raise NotImplementedError("Subclasses must implement " "'create_federation'.")

    def update_federation(self, context, federation):
        raise NotImplementedError("Subclasses must implement " "'update_federation'.")

    def delete_federation(self, context, federation):
        raise NotImplementedError("Subclasses must implement " "'delete_federation'.")

    def create_nodegroup(self, context, cluster, nodegroup):
        raise NotImplementedError("Subclasses must implement " "'create_nodegroup'.")

    def update_nodegroup(self, context, cluster, nodegroup):
        raise NotImplementedError("Subclasses must implement " "'update_nodegroup'.")

    def delete_nodegroup(self, context, cluster, nodegroup):
        raise NotImplementedError("Subclasses must implement " "'delete_nodegroup'.")

    def get_monitor(self, context, cluster):
        """return the monitor with container data for this driver."""

        return None

    def get_scale_manager(self, context, osclient, cluster):
        """return the scale manager for this driver."""

        return None

    # def rotate_ca_certificate(self, context, cluster):
    #     raise exception.NotSupported(
    #         "'rotate_ca_certificate' is not supported by this driver.")


class UbuntuFocalDriver(BaseDriver):
    @property
    def provides(self):
        return [
            {"server_type": "vm", "os": "ubuntu-focal", "coe": "kubernetes"},
        ]
