# Labels

Magnum cluster template labels are key-value pairs that are used to provide
metadata and configuration information for Kubernetes clusters created through
Magnum.

They can be used to define characteristics such as the operating system,
networking settings, container runtime, Kubernetes version, or any other custom
attributes relevant to the cluster deployment.

## Volumes

If you require your cluster to have the root filesystem on a volume, you can
specify the volume size and type using the following labels:

`boot_volume_size`

:   The size in gigabytes of the boot volume.  
    **Default value**: `[cinder]/default_boot_volume_size` from Magnum configuration.

`boot_volume_type`

:   The volume type of the boot volume.  
    **Default value**: `[cinder]/default_boot_volume_type` from Magnum configuration.

!!! note

    Volume labels cannot be changed once the cluster is deployed.  However, you
    generally do not need a large boot volume since the root filesystem is
    only used for the operating system and container runtime.

## Images

The Cluster API driver for Magnum relies on specific container images for the
deployment process.

`container_infra_prefix`

:   The prefix of the container images to use for the cluster.  
    **Default value**: `quay.io/vexxhost`

## Auditing

* `audit_log_enabled`

   Enable audit logs for the cluster.  The audit logs are stored in the
   `/var/log/kubernetes/audit/kube-apiserver-audit.log` file on the control
   plane hosts.

   Default value: `false`

* `audit_log_maxage`

   The number of days to retain audit logs.  This is only effective if the
   `audit_log_enabled` label is set to `true`.

   Default value: `30`

* `audit_log_maxbackup`

   The maximum number of audit log files to retain.  This is only effective if
   the `audit_log_enabled` label is set to `true`.

   Default value: `10`

* `audit_log_maxsize`

   The maximum size in megabytes of the audit log file before it gets rotated.
   This is only effective if the `audit_log_enabled` label is set to `true`.

   Default value: `100`

## Cloud Controller Manager

* `cloud_provider_tag`

   The tag to use for the OpenStack cloud controller provider when bootstrapping
   the cluster.

   Default value: Automatically detected based on `kube_tag` label.

## Container Networking Interface (CNI)

### Calcio

* `calico_tag`

   The version of the Calico container image to use when bootstrapping the
   cluster.

   Default value: `v3.24.2`

## Container Storage Interface (CSI)

### Cinder

* `cinder_csi_plugin_tag`

   The version of the Cinder CSI container image to use when bootstrapping the
   cluster.

   Default value: `v1.25.3`

### Manila

* `manila_csi_plugin_tag`

   The version of the Manila CSI container image to use when bootstrapping the
   cluster.

   Default value: `v1.25.3`

* `manila_csi_share_network_id`

   Manila [share network](https://wiki.openstack.org/wiki/Manila/Concepts#share_network) ID.

   Default value: `None`

## Kubernetes

* `auto_healing_enabled`

   Enable auto-healing for the cluster.  This will automatically replace failed
   nodes in the cluster with new nodes (after 5 minutes of not being ready)
   and stops further remediation if more than 40% of the cluster is unhealthy.

   Default value: `true`

* `auto_scaling_enabled`

   Enable auto-scaling for the cluster.  This will automatically scale the
   cluster up and down based on the number of pods running in the cluster.

   Default value: `false`

* `kube_tag`

   The version of Kubernetes to use.

   Default value: `v1.25.3`

* `master_lb_floating_ip_enabled`

   Attach a floating IP to the load balancer that fronts the Kubernetes API
   servers.  In order to disable this, you must be running the
   `magnum-cluster-api-proxy` service on all your Neutron network nodes.

   Default value: `true`

## OpenStack

* `fixed_subnet_cidr`

   The CIDR of the fixed subnet to use for the cluster.

   Default value: `10.0.0.0/24`

## TODO

availability_zone
dns_cluster_domain
calico_ipv4pool
