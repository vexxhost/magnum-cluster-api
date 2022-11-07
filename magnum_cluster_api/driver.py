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

import keystoneauth1
from magnum import objects as magnum_objects
from magnum.drivers.common import driver

from magnum_cluster_api import clients, monitor, objects, resources


class BaseDriver(driver.Driver):
    def __init__(self):
        self.k8s_api = clients.get_pykube_api()

    def create_cluster(self, context, cluster, cluster_create_timeout):
        osc = clients.get_openstack_api(context)

        resources.Namespace(self.k8s_api).apply()

        resources.CloudControllerManagerConfigMap(self.k8s_api, cluster).apply()
        resources.CloudControllerManagerClusterResourceSet(
            self.k8s_api, cluster
        ).apply()

        resources.CalicoConfigMap(self.k8s_api, cluster).apply()
        resources.CalicoClusterResourceSet(self.k8s_api, cluster).apply()

        resources.CinderCSIConfigMap(self.k8s_api, cluster).apply()
        resources.CinderCSIClusterResourceSet(self.k8s_api, cluster).apply()

        credential = osc.keystone().client.application_credentials.create(
            user=cluster.user_id,
            name=cluster.uuid,
            description=f"Magnum cluster ({cluster.uuid})",
        )

        resources.CloudConfigSecret(
            self.k8s_api, cluster, osc.auth_url, osc.cinder_region_name(), credential
        ).apply()

        resources.ApiCertificateAuthoritySecret(self.k8s_api, cluster).apply()
        resources.EtcdCertificateAuthoritySecret(self.k8s_api, cluster).apply()
        resources.FrontProxyCertificateAuthoritySecret(self.k8s_api, cluster).apply()
        resources.ServiceAccountCertificateAuthoritySecret(
            self.k8s_api, cluster
        ).apply()

        resources.apply_cluster_from_magnum_cluster(context, self.k8s_api, cluster)

    def update_cluster_status(self, context, cluster, use_admin_ctx=False):
        # TODO: watch for topology change instead
        osc = clients.get_openstack_api(context)

        capi_cluster = resources.Cluster(context, self.k8s_api, cluster).get_object()

        if cluster.status in (
            "CREATE_IN_PROGRESS",
            "UPDATE_IN_PROGRESS",
        ):
            capi_cluster.reload()
            status_map = {
                c["type"]: c["status"] for c in capi_cluster.obj["status"]["conditions"]
            }

            for condition in ("ControlPlaneReady", "InfrastructureReady", "Ready"):
                if status_map.get(condition) != "True":
                    return

            api_endpoint = capi_cluster.obj["spec"]["controlPlaneEndpoint"]
            cluster.api_address = (
                f"https://{api_endpoint['host']}:{api_endpoint['port']}"
            )
            cluster.coe_version = capi_cluster.obj["spec"]["topology"]["version"]

            for node_group in cluster.nodegroups:
                ng = self.update_nodegroup_status(context, cluster, node_group)
                if not ng.status.endswith("_COMPLETE"):
                    return
                if ng.status == "DELETE_COMPLETE":
                    ng.destroy()

            if cluster.status == "CREATE_IN_PROGRESS":
                cluster.status = "CREATE_COMPLETE"
            if cluster.status == "UPDATE_IN_PROGRESS":
                cluster.status = "UPDATE_COMPLETE"

            cluster.save()

        if cluster.status == "DELETE_IN_PROGRESS":
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

            resources.CloudConfigSecret(self.k8s_api, cluster).delete()
            resources.ApiCertificateAuthoritySecret(self.k8s_api, cluster).delete()
            resources.EtcdCertificateAuthoritySecret(self.k8s_api, cluster).delete()
            resources.FrontProxyCertificateAuthoritySecret(
                self.k8s_api, cluster
            ).delete()
            resources.ServiceAccountCertificateAuthoritySecret(
                self.k8s_api, cluster
            ).delete()

            cluster.status = "DELETE_COMPLETE"
            cluster.save()

    def update_cluster(self, context, cluster, scale_manager=None, rollback=False):
        raise NotImplementedError()

    def resize_cluster(
        self,
        context,
        cluster,
        resize_manager,
        node_count,
        nodes_to_remove,
        nodegroup=None,
    ):
        if nodegroup is None:
            nodegroup = cluster.default_ng_worker

        if nodes_to_remove:
            machines = objects.Machine.objects(self.k8s_api).filter(
                namespace="magnum-system",
                selector={
                    "cluster.x-self.k8s_api.io/deployment-name": resources.name_from_node_group(
                        cluster, nodegroup
                    )
                },
            )

            for machine in machines:
                instance_uuid = machine.obj["spec"]["providerID"].split("/")[-1]
                if instance_uuid in nodes_to_remove:
                    machine.obj["metadata"].setdefault("annotations", {})
                    machine.obj["metadata"]["annotations"][
                        "cluster.x-self.k8s_api.io/delete-machine"
                    ] = "yes"
                    machine.update()

        nodegroup.node_count = node_count
        self.update_nodegroup(context, cluster, nodegroup)

    def upgrade_cluster(
        self,
        context,
        cluster: magnum_objects.Cluster,
        cluster_template: magnum_objects.ClusterTemplate,
        max_batch_size,
        nodegroup: magnum_objects.NodeGroup,
        scale_manager=None,
        rollback=False,
    ):
        """
        Upgrade a cluster to a new version of Kubernetes.
        """
        # TODO: nodegroup?

        resources.apply_cluster_from_magnum_cluster(
            context, self.k8s_api, cluster, cluster_template=cluster_template
        )

    def delete_cluster(self, context, cluster):
        resources.Cluster(context, self.k8s_api, cluster).delete()

    def create_nodegroup(self, context, cluster, nodegroup):
        # TODO: update nodegroup tags
        resources.apply_cluster_from_magnum_cluster(context, self.k8s_api, cluster)

    def update_nodegroup_status(self, context, cluster, nodegroup):
        action = nodegroup.status.split("_")[0]

        if nodegroup.role == "master":
            kcp = resources.get_kubeadm_control_plane(self.k8s_api, cluster)
            if kcp is None:
                return nodegroup

            ready = kcp.obj["status"].get("ready", False)
            failure_message = kcp.obj["status"].get("failureMessage")

            if ready:
                nodegroup.status = f"{action}_COMPLETE"
            nodegroup.status_reason = failure_message
        else:
            md = resources.get_machine_deployment(self.k8s_api, cluster, nodegroup)
            if md is None:
                if action == "DELETE":
                    nodegroup.status = f"{action}_COMPLETE"
                    nodegroup.save()
                    return nodegroup
                return nodegroup

            phase = md.obj["status"]["phase"]

            if phase in ("ScalingUp", "ScalingDown"):
                nodegroup.status = f"{action}_IN_PROGRESS"
            elif phase == "Running":
                nodegroup.status = f"{action}_COMPLETE"
            elif phase in ("Failed", "Unknown"):
                nodegroup.status = f"{action}_FAILED"

        nodegroup.save()

        return nodegroup

    def update_nodegroup(self, context, cluster, nodegroup):
        # TODO
        resources.apply_cluster_from_magnum_cluster(context, self.k8s_api, cluster)

    def delete_nodegroup(self, context, cluster, nodegroup):
        nodegroup.status = "DELETE_IN_PROGRESS"
        nodegroup.save()

        resources.apply_cluster_from_magnum_cluster(
            context,
            self.k8s_api,
            cluster,
        )

    def get_monitor(self, context, cluster):
        return monitor.ClusterApiMonitor(context, cluster)

    # def rotate_ca_certificate(self, context, cluster):
    #     raise exception.NotSupported(
    #         "'rotate_ca_certificate' is not supported by this driver.")

    def create_federation(self, context, federation):
        raise NotImplementedError()

    def update_federation(self, context, federation):
        raise NotImplementedError()

    def delete_federation(self, context, federation):
        raise NotImplementedError()


class UbuntuFocalDriver(BaseDriver):
    @property
    def provides(self):
        return [
            {"server_type": "vm", "os": "ubuntu-focal", "coe": "kubernetes"},
        ]
