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
from tenacity import retry, stop_after_delay, wait_fixed

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

    @cluster_lock_wrapper
    def update_cluster_status(
        self, context, cluster: magnum_objects.Cluster, use_admin_ctx: bool = False
    ):
        # NOTE(mnaser): We may be called with a stale cluster object, so we
        #               need to refresh it to make sure we have the latest data.
        cluster.refresh()

        node_groups = [
            self.update_nodegroup_status(context, cluster, node_group)
            for node_group in cluster.nodegroups
        ]
        # TODO: watch for topology change instead
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
                    machine.update()

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
        """
        # TODO: nodegroup?

        # Get current generation
        current_generation = resources.Cluster(
            context, self.k8s_api, cluster
        ).get_observed_generation()
        resources.apply_cluster_from_magnum_cluster(
            context, self.k8s_api, cluster, cluster_template=cluster_template
        )
        # Wait till the generation has been increased
        self.wait_capi_cluster_reconciliation_start(
            context, cluster, current_generation
        )

        # NOTE(mnaser): We need to save the cluster status here to make sure
        #               it happens inside the lock.
        cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        cluster.save()

    @retry(
        stop=stop_after_delay(10),
        wait=wait_fixed(1),
    )
    def wait_capi_cluster_reconciliation_start(
        self, context, cluster: magnum_objects.Cluster, old_generation: int
    ):
        """Wait until the cluster's new generation is observed by capi-controller

        This means the cluster reconciliation has been started and the conditions has been updated.
        """
        current_generation = resources.Cluster(
            context, self.k8s_api, cluster
        ).get_observed_generation()
        if old_generation != current_generation:
            return
        raise exceptions.ClusterAPIReconcileTimeout()

    @cluster_lock_wrapper
    def delete_cluster(self, context, cluster: magnum_objects.Cluster):
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
        utils.validate_nodegroup(nodegroup, context)

        cluster_resource: objects.Cluster = objects.Cluster.objects(
            self.k8s_api, namespace="magnum-system"
        ).get(name=cluster.stack_id)

        cluster_resource.obj["spec"]["topology"]["workers"][
            "machineDeployments"
        ].append(resources.mutate_machine_deployment(context, cluster, nodegroup))

        current_generation = resources.Cluster(
            context, self.k8s_api, cluster
        ).get_observed_generation()
        cluster_resource.update()
        self.wait_capi_cluster_reconciliation_start(
            context, cluster, current_generation
        )

        nodegroup.status = fields.ClusterStatus.CREATE_IN_PROGRESS
        nodegroup.save()

        cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        cluster.save()

    def update_nodegroup_status(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        action = nodegroup.status.split("_")[0]

        if nodegroup.role == "master":
            kcp = resources.get_kubeadm_control_plane(self.k8s_api, cluster)
            if kcp is None:
                return nodegroup

            generation = kcp.obj.get("status", {}).get("observedGeneration", 1)
            if generation > 1:
                action = "UPDATE"

            ready = kcp.obj["status"].get("ready", False)
            failure_message = kcp.obj["status"].get("failureMessage")

            updated_replicas = kcp.obj["status"].get("updatedReplicas")
            replicas = kcp.obj["status"].get("replicas")

            if updated_replicas != replicas:
                nodegroup.status = f"{action}_IN_PROGRESS"
            elif updated_replicas == replicas and ready:
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

    @cluster_lock_wrapper
    def update_nodegroup(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        self._update_nodegroup(context, cluster, nodegroup)

    def _update_nodegroup(
        self,
        context,
        cluster: magnum_objects.Cluster,
        nodegroup: magnum_objects.NodeGroup,
    ):
        utils.validate_nodegroup(nodegroup, context)

        cluster_resource: objects.Cluster = objects.Cluster.objects(
            self.k8s_api, namespace="magnum-system"
        ).get(name=cluster.stack_id)

        machine_deployment_index = None
        for i, machine_deployment in enumerate(
            cluster_resource.obj["spec"]["topology"]["workers"]["machineDeployments"]
        ):
            if machine_deployment["name"] == nodegroup.name:
                machine_deployment_index = i
                break

        if machine_deployment_index is not None:
            machine_deployment = cluster_resource.obj["spec"]["topology"]["workers"][
                "machineDeployments"
            ][machine_deployment_index]

            cluster_resource.obj["spec"]["topology"]["workers"]["machineDeployments"][
                machine_deployment_index
            ] = resources.mutate_machine_deployment(
                context,
                cluster,
                nodegroup,
                machine_deployment,
            )

        current_generation = resources.Cluster(
            context, self.k8s_api, cluster
        ).get_observed_generation()
        cluster_resource.update()
        self.wait_capi_cluster_reconciliation_start(
            context, cluster, current_generation
        )

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
        cluster_resource: objects.Cluster = objects.Cluster.objects(
            self.k8s_api, namespace="magnum-system"
        ).get(name=cluster.stack_id)

        machine_deployment_index = None
        for i, machine_deployment in enumerate(
            cluster_resource.obj["spec"]["topology"]["workers"]["machineDeployments"]
        ):
            if machine_deployment["name"] == nodegroup.name:
                machine_deployment_index = i
                break

        if machine_deployment_index is not None:
            del cluster_resource.obj["spec"]["topology"]["workers"][
                "machineDeployments"
            ][machine_deployment_index]

        current_generation = resources.Cluster(
            context, self.k8s_api, cluster
        ).get_observed_generation()
        cluster_resource.update()
        self.wait_capi_cluster_reconciliation_start(
            context, cluster, current_generation
        )

        nodegroup.status = fields.ClusterStatus.DELETE_IN_PROGRESS
        nodegroup.save()

        cluster.status = fields.ClusterStatus.UPDATE_IN_PROGRESS
        cluster.save()

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
