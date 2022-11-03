from magnum.conductor import monitors
from magnum.objects import fields

from magnum_cluster_api import clients, resources, utils


class ClusterApiMonitor(monitors.MonitorBase):
    def __init__(self, context, cluster):
        super(ClusterApiMonitor, self).__init__(context, cluster)
        self.data = {}
        self.k8s_api = clients.get_pykube_api()

    def metrics_spec(self):
        raise NotImplementedError()

    def pull_data(self):
        raise NotImplementedError()

    def _return_health_status(self, status, message):
        self.data["health_status"] = status
        self.data["health_status_reason"] = {"status": message}

    def poll_health_status(self):
        """
        Poll for the health status of the cluster using the MachineHealthCheck
        API using the management cluster.
        """
        AUTO_HEAL_DISABLED = "The cluster does not have auto healing enabled"
        NODES_UNHEALTHY = "The cluster has unhealthy nodes"
        HEALTH_OK = "All nodes are healthy"

        if not utils.get_cluster_label_as_bool(
            self.cluster, "auto_healing_enabled", True
        ):
            return self._return_health_status(
                fields.ClusterHealthStatus.UNKNOWN,
                AUTO_HEAL_DISABLED,
            )

        mhc = resources.MachineHealthCheck(self.k8s_api, self.cluster).get_object()
        if not mhc.exists():
            return self._return_health_status(
                fields.ClusterHealthStatus.UNKNOWN,
                AUTO_HEAL_DISABLED,
            )

        mhc.reload()

        current_healthy = mhc.obj["status"]["currentHealthy"]
        expected_machines = mhc.obj["status"]["expectedMachines"]

        if current_healthy != expected_machines:
            return self._return_health_status(
                fields.ClusterHealthStatus.UNHEALTHY,
                NODES_UNHEALTHY,
            )

        return self._return_health_status(
            fields.ClusterHealthStatus.HEALTHY,
            HEALTH_OK,
        )
