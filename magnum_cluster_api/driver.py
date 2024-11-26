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


from __future__ import annotations

import keystoneauth1
from magnum import objects as magnum_objects
from magnum.conductor import scale_manager
from magnum.drivers.common import driver
from magnum.objects import fields

from magnum_cluster_api import (
    clients,
    exceptions,
    monitor,
    objects,
    resources,
    sync,
    utils,
)


def cluster_lock_wrapper(func):
    def wrapper(*args, **kwargs):
        cluster = args[2]  # Assuming cluster is the second argument
        with sync.ClusterLock(cluster.uuid):
            return func(*args, **kwargs)

    return wrapper


class BaseDriver(driver.Driver):
    def __init__(self):
        self.k8s_api = clients.get_pykube_api()

    def create_cluster(
        self, context, cluster: magnum_objects.Cluster, cluster_create_timeout: int
    ):
        """
        Create cluster.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """
        # NOTE(mnaser): We want to set the `stack_id` as early as possible to
        #               make sure we can use it in the cluster creation.
        cluster.stack_id = utils.generate_cluster_api_name(self.k8s_api)
        cluster.save()

        utils.validate_cluster(context, cluster)
        resources.Namespace(self.k8s_api).apply()

        return self._create_cluster(context, cluster)

    @cluster_lock_wrapper
    def _create_cluster(self, context, cluster: magnum_objects.Cluster):
        osc = clients.get_openstack_api(context)

        credential = osc.keystone().client.application_credentials.create(
            user=cluster.user_id,
            name=cluster.uuid,
            description=f"Magnum cluster ({cluster.uuid})",
        )

        resources.CloudConfigSecret(
            context,
            self.k8s_api,
            cluster,
            osc.cinder_region_name(),
            credential,
        ).apply()

        resources.ApiCertificateAuthoritySecret(context, self.k8s_api, cluster).apply()
        resources.EtcdCertificateAuthoritySecret(context, self.k8s_api, cluster).apply()
        resources.FrontProxyCertificateAuthoritySecret(
            context, self.k8s_api, cluster
        ).apply()
        resources.ServiceAccountCertificateAuthoritySecret(
            context, self.k8s_api, cluster
        ).apply()

        resources.apply_cluster_from_magnum_cluster(
            context, self.k8s_api, cluster, skip_auto_scaling_release=True
        )

    def _get_cluster_status_reason(self, capi_cluster):
        capi_cluster_status_reason = ""
        capi_ops_cluster_status_reason = ""

        # Get the latest event message of the CAPI Cluster
        capi_cluster_events = capi_cluster.events
        if capi_cluster_events:
            capi_cluster_status_reason += utils.format_event_message(
                list(capi_cluster_events)[-1]
            )

        # Get the latest event message of the CAPI OpenstackCluster
        capi_ops_cluster_events = []
        capi_ops_cluster = capi_cluster.openstack_cluster
        if capi_ops_cluster:
            capi_ops_cluster_events = capi_ops_cluster.events
        if capi_ops_cluster_events:
            capi_ops_cluster_status_reason += utils.format_event_message(
                list(capi_ops_cluster_events)[-1]
            )

        return "CAPI Cluster status: %s. CAPI OpenstackCluster status reason: %s" % (
            capi_cluster_status_reason,
            capi_ops_cluster_status_reason,
        )

    def update_cluster_control_plane_status(
        self,
        context,
        cluster: magnum_objects.Cluster,
    ):
        nodegroup = cluster.default_ng_master
        action = nodegroup.status.split("_")[0]

        kcp = resources.get_kubeadm_control_plane(self.k8s_api, cluster)
        if kcp is None:
            return nodegroup

        generation = kcp.obj.get("status", {}).get("observedGeneration", 1)
        if generation > 1:
            action = "UPDATE"

        ready = kcp.obj.get("status", {}).get("ready", False)
        failure_message = kcp.obj.get("status", {}).get("failureMessage")

        updated_replicas = kcp.obj.get("status", {}).get("updatedReplicas")
        replicas = kcp.obj.get("status", {}).get("replicas")

        if updated_replicas != replicas:
            nodegroup.status = f"{action}_IN_PROGRESS"
        elif updated_replicas == replicas and ready:
            nodegroup.status = f"{action}_COMPLETE"
        nodegroup.status_reason = failure_message

        nodegroup.save()

        return nodegroup

    @cluster_lock_wrapper
    def update_cluster_status(
        self, context, cluster: magnum_objects.Cluster, use_admin_ctx: bool = False
    ):
        # NOTE(mnaser): We may be called with a stale cluster object, so we
        #               need to refresh it to make sure we have the latest data.
        cluster.refresh()

        # TODO: watch for topology change instead
        node_groups = [
            self.update_cluster_control_plane_status(context, cluster)
        ] + self.update_nodegroups_status(context, cluster)
        osc = clients.get_openstack_api(context)

        capi_cluster = resources.Cluster(context, self.k8s_api, cluster).get_or_none()

        if cluster.status in (
            fields.ClusterStatus.CREATE_IN_PROGRESS,
            fields.ClusterStatus.UPDATE_IN_PROGRESS,
        ):
            # NOTE(mnaser): It's possible we run a cluster status update before
            #               the cluster is created. In that case, we don't want
            #               to update the cluster status.
            if capi_cluster is None:
                return

            capi_cluster.reload()
            status_map = {
                c["type"]: c["status"] for c in capi_cluster.obj["status"]["conditions"]
            }

            for condition in ("ControlPlaneReady", "InfrastructureReady", "Ready"):
                if status_map.get(condition) != "True":
                    cluster.status_reason = self._get_cluster_status_reason(
                        capi_cluster
                    )
                    cluster.save()
                    return

            api_endpoint = capi_cluster.obj["spec"]["controlPlaneEndpoint"]
            cluster.api_address = (
                f"https://{api_endpoint['host']}:{api_endpoint['port']}"
            )
            cluster.coe_version = capi_cluster.obj["spec"]["topology"]["version"]

            # NOTE(oleks): To avoid autoscaler crashes, we deploy it after the
            #              cluster api endpoint is reachable.
            if (
                cluster.status == fields.ClusterStatus.CREATE_IN_PROGRESS
                and utils.get_auto_scaling_enabled(cluster)
            ):
                resources.ClusterAutoscalerHelmRelease(self.k8s_api, cluster).apply()

            for ng in node_groups:
                if not ng.status.endswith("_COMPLETE"):
                    return
                if ng.status == fields.ClusterStatus.DELETE_COMPLETE:
                    ng.destroy()

            if cluster.status == fields.ClusterStatus.CREATE_IN_PROGRESS:
                cluster.status_reason = None
                cluster.status = fields.ClusterStatus.CREATE_COMPLETE
            if cluster.status == fields.ClusterStatus.UPDATE_IN_PROGRESS:
                cluster.status_reason = None
                cluster.status = fields.ClusterStatus.UPDATE_COMPLETE

            cluster.save()

        if cluster.status == fields.ClusterStatus.DELETE_IN_PROGRESS:
            if capi_cluster and capi_cluster.exists():
                cluster.status_reason = self._get_cluster_status_reason(capi_cluster)
                cluster.save()
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

            resources.CloudConfigSecret(context, self.k8s_api, cluster).delete()
            resources.ApiCertificateAuthoritySecret(
                context, self.k8s_api, cluster
            ).delete()
            resources.EtcdCertificateAuthoritySecret(
                context, self.k8s_api, cluster
            ).delete()
            resources.FrontProxyCertificateAuthoritySecret(
                context, self.k8s_api, cluster
            ).delete()
            resources.ServiceAccountCertificateAuthoritySecret(
                context, self.k8s_api, cluster
            ).delete()
            resources.ClusterServerGroups(context, cluster).delete()

            cluster.status_reason = None
            cluster.status = fields.ClusterStatus.DELETE_COMPLETE
            cluster.save()

    @cluster_lock_wrapper
    def update_cluster(
        self,
        context,
        cluster: magnum_objects.Cluster,
        scale_manager=None,
        rollback=False,
    ):
        """
        Update cluster.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """
        raise NotImplementedError()

    @cluster_lock_wrapper
    def resize_cluster(
        self,
        context,
        cluster: magnum_objects.Cluster,
        resize_manager: scale_manager.ScaleManager,
        node_count: int,
        nodes_to_remove: list[str],
        nodegroup: magnum_objects.NodeGroup = None,
    ):
        """
        Resize cluster (primarily add or remove nodes).

        The cluster object passed to this method is already not in `UPDATE_IN_PROGRESS`
        state and the node group object passed to this method is in `UPDATE_IN_PROGRESS`
        state and saved.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """
        utils.validate_cluster(context, cluster)

        if nodes_to_remove:
            machines = objects.Machine.objects(self.k8s_api).filter(
                namespace="magnum-system",
                selector={
                    "cluster.x-k8s.io/cluster-name": cluster.stack_id,
                    "topology.cluster.x-k8s.io/deployment-name": nodegroup.name,
                },
            )

            for machine in machines:
                instance_uuid = machine.obj["spec"]["providerID"].split("/")[-1]
                if instance_uuid in nodes_to_remove:
                    machine.obj["metadata"].setdefault("annotations", {})
                    machine.obj["metadata"]["annotations"][
                        "cluster.x-k8s.io/delete-machine"
                    ] = "yes"
                    utils.kube_apply_patch(machine)

        self._update_nodegroup(context, cluster, nodegroup)

    @cluster_lock_wrapper
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

        The only label that we change during the upgrade is the `kube_tag` label.

        Historically, the upgrade cluster has been a "hammer" that was used to sync the
        Kubernetes Cluster API objects with the Magnum objects.  However, by doing this,
        we're losing the ability to maintain the existing labels of the cluster.

        For now, upgrade cluster simply modifies the labels that are necessary for the
        upgrade, nothing else.  For the future, we can perhaps use the `update_cluster`
        API.

        This method is called synchonously by the Magnum API, therefore it will be blocking
        the Magnum API, so it should be as fast as possible.
        """
        # XXX(mnaser): The Magnum API historically only did upgrade one node group at a
        #              time.  This is a limitation of the Magnum API and not the Magnum
        #              Cluster API since doing multiple rolling upgrades was not very
        #              well supported in the past.
        #
        #              The Magnum Cluster API does not have this limitation in this case
        #              we ignore the `nodegroup` parameter and upgrade the entire cluster
        #              at once.
        cluster.cluster_template_id = cluster_template.uuid
        cluster.labels["kube_tag"] = cluster_template.labels["kube_tag"]

        for ng in cluster.nodegroups:
            ng.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
            ng.image_id = cluster_template.image_id
            ng.labels["kube_tag"] = cluster_template.labels["kube_tag"]
            ng.save()

        # NOTE(mnaser): We run a full apply on the cluster regardless of the changes, since
        #               the expectation is that running an upgrade operation will change
        #               the cluster in some way.
        resources.apply_cluster_from_magnum_cluster(context, self.k8s_api, cluster)

        # NOTE(mnaser): We do not save the cluster object here because the Magnum driver
        #               will save the object that it passed to us here.

    @cluster_lock_wrapper
    def delete_cluster(self, context, cluster: magnum_objects.Cluster):
        """
        Delete cluster.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """
        if cluster.stack_id is None:
            return
        # NOTE(mnaser): This should be removed when this is fixed:
        #
        #               https://github.com/kubernetes-sigs/cluster-api-provider-openstack/issues/842
        #               https://github.com/kubernetes-sigs/cluster-api-provider-openstack/pull/990
        utils.delete_loadbalancers(context, cluster)

        resources.ClusterResourceSet(self.k8s_api, cluster).delete()
        resources.ClusterResourcesConfigMap(context, self.k8s_api, cluster).delete()
        resources.Cluster(context, self.k8s_api, cluster).delete()
        resources.ClusterAutoscalerHelmRelease(self.k8s_api, cluster).delete()

    @cluster_lock_wrapper
    def create_nodegroup(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        """
        Create node group.

        The cluster object passed to this method is already in `UPDATE_IN_PROGRESS` state
        and the node group object passed to this method is in `CREATE_IN_PROGRESS` state.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """
        utils.validate_nodegroup(nodegroup, context)
        utils.ensure_worker_server_group(
            ctx=context, cluster=cluster, node_group=nodegroup
        )

        cluster_resource = objects.Cluster.for_magnum_cluster(self.k8s_api, cluster)
        cluster_resource.obj["spec"]["topology"]["workers"][
            "machineDeployments"
        ].append(resources.mutate_machine_deployment(context, cluster, nodegroup))

        utils.kube_apply_patch(cluster_resource)

    def update_nodegroups_status(
        self, context, cluster: magnum_objects.Cluster
    ) -> list[magnum_objects.NodeGroup]:
        cluster_resource = objects.Cluster.for_magnum_cluster_or_none(
            self.k8s_api, cluster
        )
        if cluster_resource is None:
            return cluster.nodegroups

        node_groups = []
        for node_group in cluster.nodegroups:
            # NOTE(mnaser): Nothing to do if the node group is in `DELETE_COMPLETE`
            #               state and skip work if it's a master node group.
            if (
                node_group.role == "master"
                or node_group.status == fields.ClusterStatus.DELETE_COMPLETE
            ):
                continue

            node_groups.append(node_group)

            md = objects.MachineDeployment.for_node_group_or_none(
                self.k8s_api, cluster, node_group
            )

            # NOTE(mnaser): If the cluster is in `DELETE_IN_PROGRESS` state, we need to
            #               wait for the `MachineDeployment` to be deleted before we can
            #               mark the node group as `DELETE_COMPLETE`.
            if (
                node_group.status == fields.ClusterStatus.DELETE_IN_PROGRESS
                and md is None
            ):
                utils.delete_worker_server_group(
                    ctx=context, cluster=cluster, node_group=node_group
                )
                node_group.status = fields.ClusterStatus.DELETE_COMPLETE
                node_group.save()
                continue

            md_is_running = (
                md is not None and md.obj.get("status", {}).get("phase") == "Running"
            )

            # NOTE(mnaser): If the node group is in `CREATE_IN_PROGRESS` state, we need to
            #               wait for the `MachineDeployment` to be hit the `Running` phase
            #               before we can mark the node group as `CREATE_COMPLETE`.
            if (
                node_group.status == fields.ClusterStatus.CREATE_IN_PROGRESS
                and md_is_running
            ):
                node_group.status = fields.ClusterStatus.CREATE_COMPLETE
                node_group.save()
                continue

            # Get list of all of the OpenStackMachine objects for this node group
            machines = objects.OpenStackMachine.objects(
                self.k8s_api, namespace="magnum-system"
            ).filter(
                selector={
                    "cluster.x-k8s.io/cluster-name": cluster.stack_id,
                    "topology.cluster.x-k8s.io/deployment-name": node_group.name,
                },
            )

            # Ensure that the image ID from the spec matches all of the OpenStackMachine objects
            # for this node group
            md_spec = cluster_resource.get_machine_deployment_spec(node_group.name)
            md_variables = {
                i["name"]: i["value"] for i in md_spec["variables"]["overrides"]
            }
            image_id_match = all(
                [
                    machine.obj["spec"]["image"]["id"] == md_variables["imageUUID"]
                    for machine in machines
                ]
            )

            # NOTE(mnaser): If the cluster is in `UPDATE_IN_PROGRESS` state, we need to
            #               wait for the `MachineDeployment` to match the desired state
            #               from the `Cluster` resource and that it is in the `Running`
            #               phase before we can mark the node group as `UPDATE_COMPLETE`.
            if (
                node_group.status == fields.ClusterStatus.UPDATE_IN_PROGRESS
                and md_is_running
                and md.equals_spec(
                    cluster_resource.get_machine_deployment_spec(node_group.name)
                )
                and image_id_match
            ):
                node_group.status = fields.ClusterStatus.UPDATE_COMPLETE
                node_group.save()
                continue

        return node_groups

    @cluster_lock_wrapper
    def update_nodegroup(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        """
        Update node group (primarily resize it)

        This cluster object passed to this method is already in `UPDATE_IN_PROGRESS` state
        and the node group object passed to this method is in `UPDATE_IN_PROGRESS` state
        but it's not saved.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """
        self._update_nodegroup(context, cluster, nodegroup)

    def _update_nodegroup(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        utils.validate_nodegroup(nodegroup, context)
        utils.ensure_worker_server_group(
            ctx=context, cluster=cluster, node_group=nodegroup
        )

        cluster_resource = objects.Cluster.for_magnum_cluster(self.k8s_api, cluster)

        current_md_spec = cluster_resource.get_machine_deployment_spec(nodegroup.name)
        target_md_spec = resources.mutate_machine_deployment(
            context,
            cluster,
            nodegroup,
            cluster_resource.get_machine_deployment_spec(nodegroup.name),
        )

        if current_md_spec == target_md_spec:
            return

        cluster_resource.set_machine_deployment_spec(nodegroup.name, target_md_spec)
        utils.kube_apply_patch(cluster_resource)

        nodegroup.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        nodegroup.save()

        cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        cluster.save()

    @cluster_lock_wrapper
    def delete_nodegroup(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        """
        Delete node group.

        The cluster resource that is passed to this method is already in `UPDATE_IN_PROGRESS`
        however the node group object passed to this method is in `DELETE_IN_PROGRESS` state
        but it's not saved.

        This method is called asynchonously by the Magnum API, therefore it will not be
        blocking the Magnum API.
        """

        # NOTE(mnaser): We want to switch the node group to `DELETE_IN_PROGRESS` state
        #               as soon as possible to make sure that the Magnum API knows that
        #               the node group is being deleted.
        nodegroup.status = fields.ClusterStatus.DELETE_IN_PROGRESS
        nodegroup.save()

        cluster_resource = objects.Cluster.for_magnum_cluster(self.k8s_api, cluster)

        try:
            md_index = cluster_resource.get_machine_deployment_index(nodegroup.name)
        except exceptions.MachineDeploymentNotFound:
            nodegroup.status = fields.ClusterStatus.DELETE_COMPLETE
            nodegroup.save()
            return

        del cluster_resource.obj["spec"]["topology"]["workers"]["machineDeployments"][
            md_index
        ]

        utils.kube_apply_patch(cluster_resource)

    @cluster_lock_wrapper
    def get_monitor(self, context, cluster: magnum_objects.Cluster):
        return monitor.Monitor(context, cluster)

    # def rotate_ca_certificate(self, context, cluster):
    #     raise exception.NotSupported(
    #         "'rotate_ca_certificate' is not supported by this driver.")

    def create_federation(self, context, federation):
        raise NotImplementedError()

    def update_federation(self, context, federation):
        raise NotImplementedError()

    def delete_federation(self, context, federation):
        raise NotImplementedError()


class UbuntuDriver(BaseDriver):
    @property
    def provides(self):
        return [
            {"server_type": "vm", "os": "ubuntu", "coe": "kubernetes"},
        ]


class UbuntuFocalDriver(UbuntuDriver):
    @property
    def provides(self):
        return [
            {"server_type": "vm", "os": "ubuntu-focal", "coe": "kubernetes"},
        ]


class FlatcarDriver(BaseDriver):
    @property
    def provides(self):
        return [
            {"server_type": "vm", "os": "flatcar", "coe": "kubernetes"},
        ]


class RockyLinuxDriver(BaseDriver):
    @property
    def provides(self):
        return [
            {"server_type": "vm", "os": "rockylinux", "coe": "kubernetes"},
        ]
