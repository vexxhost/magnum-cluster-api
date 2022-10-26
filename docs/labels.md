# Labels

## Auditing

* `audit_log_enabled`

   Enable audit logs for the cluster.  The audit logs are stored in the
   `/var/log/kubernetes/audit/kube-apiserver-audit.log` file on the control
   plane hosts.

   Default value: `false`

* `audit_log_maxage`

   The number of days to retain audit logs.  This is only effective if the
   `audit_logs_enabled` label is set to `true`.

   Default value: `30`

* `audit_log_maxbackup`

   The maximum number of audit log files to retain.  This is only effective if
   the `audit_logs_enabled` label is set to `true`.

   Default value: `10`

* `audit_log_maxsize`

   The maximum size in megabytes of the audit log file before it gets rotated.
   This is only effective if the `audit_logs_enabled` label is set to `true`.

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

## Kubernetes

* `kube_tag`

   The version of Kubernetes to use.

   Default value: `v1.25.3`

## TODO

availability_zone
fixed_subnet_cidr
dns_cluster_domain
calico_ipv4pool
