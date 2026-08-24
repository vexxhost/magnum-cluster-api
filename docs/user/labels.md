# Labels

Magnum cluster template labels are key-value pairs that are used to provide
metadata and configuration information for Kubernetes clusters created through
Magnum.

They can be used to define characteristics such as the operating system,
networking settings, container runtime, Kubernetes version, or any other custom
attributes relevant to the cluster deployment.

## Cluster add-on profiles

The optional `addon_profiles` label selects an ordered, `+`-separated set of
operator-approved add-on selectors. Each selector can name either one
installable lifecycle profile or one immutable profile set that expands to an
ordered list of profiles. It must be set on an immutable cluster template; a
cluster create request cannot introduce, remove, reorder, or override the
selection. When omitted, cluster create, update, and delete behavior is
unchanged. The unsupported singular `addon_profile` spelling is rejected.

For upgrade safety only, deletion of an already-provisioned cluster carrying
the legacy singular label can migrate its existing one-profile lifecycle
annotations into the immutable plural snapshot. Migration requires the legacy
profile, HelmChartProxy, release, and selector-label identities to match the
currently published profile exactly. This compatibility path cannot be used to
create a new cluster or change the selected profile.

Profiles and optional profile sets are stored in
`magnum-system/mcapi-addon-profiles` under the `profiles.yaml` key. The
document uses explicit schema version 1. Each profile may add only labels in the
`addons.magnum-cluster-api.openstack.org/` domain and identifies one required
Cluster API Add-on Provider for Helm `HelmChartProxy` and release name. A
profile can declare selected dependencies and generic capabilities that must
be supplied by another immutable cluster contract:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcapi-addon-profiles
  namespace: magnum-system
data:
  profiles.yaml: |
    schemaVersion: 1
    profiles:
      example-foundation-v1-deadbeef:
        category: platform-foundation
        dependsOn: []
        requiresCapabilities: []
        clusterLabels:
          addons.magnum-cluster-api.openstack.org/foundation: deadbeef
        requiredHelmChartProxy: example-foundation-v1-deadbeef
        releaseName: example-foundation
        createTimeout: 45m
        deleteTimeout: 20m
      example-workload-v1-cafebabe:
        category: workload-platform
        dependsOn:
          - example-foundation-v1-deadbeef
        requiresCapabilities: []
        clusterLabels:
          addons.magnum-cluster-api.openstack.org/workload: cafebabe
        requiredHelmChartProxy: example-workload-v1-cafebabe
        releaseName: example-workload
        createTimeout: 90m
        deleteTimeout: 30m
    profileSets:
      example-platform-stack-v1-01234567:
        profiles:
          - example-foundation-v1-deadbeef
          - example-workload-v1-cafebabe
```

For example, an immutable template can select both profiles with
`addon_profiles=example-foundation-v1-deadbeef+example-workload-v1-cafebabe`.
The equivalent profile-set selection is
`addon_profiles=example-platform-stack-v1-01234567`. Ordinary profiles and
profile sets can be composed in the same label. Profile and profile-set names
share one selector namespace and cannot collide. A profile set contains only
ordinary profile names; nested sets are not supported.

Every dependency must be present after expansion; dependencies are not added
implicitly. Each published profile set must also contain a complete dependency
selection so it is valid on its own. Empty entries, duplicate selectors,
overlapping expansions, cycles, colliding selector labels, and reused
`HelmChartProxy` identities are rejected.

The driver stores the requested selectors, expanded profiles, selected
profile-set definitions, complete canonical contract, dependency waves, and
SHA-256 digest on the initial Cluster API `Cluster`. The existing four-field
schema-version-1 snapshot remains byte-for-byte unchanged when only ordinary
profiles are selected; the selector and set fields are present only when a set
was used. Later reconcile and deletion use the snapshot rather than rereading
the mutable ConfigMap. Profiles in one dependency wave activate together; the
next wave activates only after every profile in the current wave is ready.

For selected clusters, Magnum remains `CREATE_IN_PROGRESS` until each matching,
current-generation `HelmReleaseProxy` reports `Ready=True`. Controller-reported
credential, reachability, and Helm install errors remain pending so CAAPH can
retry them until that profile's `createTimeout`; a timeout then produces
`CREATE_FAILED` while retaining the cluster. Contract violations such as an
unapproved proxy, duplicate match, stale snapshot, or release identity mismatch
fail immediately. On delete, the driver removes selector labels and waits for
release proxies in exact reverse dependency-wave order before deleting Cluster
API resources. With the
`Continuous` strategy, CAAPH uninstalls the release as part of that deletion.
CAAPH intentionally retains an orphaned `InstallOnce` proxy, so the driver
requests deletion of the identity-validated proxy and removes only CAAPH's
finalizer. This deliberately skips Helm uninstall because the workload cluster
is being destroyed and preserves `InstallOnce` semantics for the workload
release.

Profile and profile-set names and content are an operator contract. Use
content-addressed names and never change an existing item in place. Schema
version 1 accepts at most 16 profiles, 16 profile sets, 16 selectors, and 16
expanded profiles; at most 16 members per set; 16 dependencies and labels per
profile; 32 capability requirements per profile; a 64 KiB source document; a
128 KiB resolved snapshot; and positive `s`, `m`, or `h` timeouts no longer
than 24h.

## Machine network profiles

The optional `machine_network_profile` label selects one operator-approved set
of additional OpenStack ports for cluster Machines. It must be set on the
immutable cluster template and cannot be introduced or overridden by a cluster
create request. Omitting the label preserves the existing Cluster API Provider
OpenStack networking path without reading the profile ConfigMap or rendering
the new topology variables.

Profiles are stored in `magnum-system/mcapi-machine-network-profiles` under the
`profiles.yaml` key. Schema version 1 supports additive ports and explicit
control-plane, worker, or named node-group scope:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcapi-machine-network-profiles
  namespace: magnum-system
data:
  profiles.yaml: |
    schemaVersion: 1
    profiles:
      example-secondary-v1-deadbeef:
        mode: augment
        appliesTo: all
        providesCapabilities:
          - machine-network.example.org/secondary
        additionalPorts:
          - role: data
            networkID: 11111111-1111-4111-8111-111111111111
            fixedIPs:
              - subnetID: 22222222-2222-4222-8222-222222222222
            vnicType: normal
            portSecurityEnabled: false
```

`appliesTo` accepts `all`, `control-plane`, `workers`, or
`nodegroup:<name>`. Port roles are stable DNS labels and must be unique within
the profile. Version 1 accepts network and optional subnet UUIDs, `vnicType`,
and `portSecurityEnabled`; it does not accept pre-created port IDs or literal
addresses. CAPO creates a distinct port and allocation for each applicable
Machine.

CAPO treats an explicit `OpenStackMachineTemplate.spec.template.spec.ports`
list as the complete machine-port definition and does not add its normal
cluster-network port. Therefore, selecting a machine network profile requires
an existing fixed primary network. The driver renders that primary network and
optional fixed subnet first, followed by the profile's additional ports. A
profile that duplicates the primary network and subnet is rejected. Clusters
that let mCAPI create a managed primary network cannot select a version 1
machine network profile.

The normalized profile and SHA-256 digest are stored on the initial Cluster API
`Cluster`. Reconcile, replacement, scale, and later node-group creation use the
persisted snapshot instead of rereading a changed ConfigMap. The combined
machine-network and add-on contract identities are also covered by a bundle
digest. Add-on `requiresCapabilities` values must be supplied by the selected
machine network profile before infrastructure creation.

## Volumes

If you require your cluster to have the root filesystem on a volume, you can
specify the volume size and type using the following labels:

`boot_volume_size`

:   The size in gigabytes of the boot volume.  If you set this value, it will
    enable boot from volume.
    **Default value**: Unset

`boot_volume_type`

:   The volume type of the boot volume.
    **Default value**: Default volume

`boot_volume_availability_zone`

:   The availability zone for the boot volume.  This is useful when the volume
    type backend is tied to a specific availability zone that differs from the
    compute availability zone.
    **Default value**: Falls back to `availability_zone` label, then empty string.

`etcd_volume_size`

:   The size in gigabytes of the `etcd` volume.  If you set this value, it will
    create a volume for `etcd` specifically and mount it on the system.
    **Default value**: Unset

`etcd_volume_type`

:   The volume type of the `etcd` volume, this can be useful if you want to use an
    encrypted or high performance volume type.
    **Default value**: None

!!! note

    Volume labels cannot be changed once the cluster is deployed.  However, you
    generally do not need a large boot volume since the root filesystem is
    only used for the operating system and container runtime.

## Images

The Cluster API driver for Magnum relies on specific container images for the
deployment process.

`container_infra_prefix`

:   The prefix of the container images to use for the cluster.
    **Default value**: None, defaults to upstream images.

## Network

The way containers talk to each other and the outside world is defined by the networking setup.
This setup decides how information is shared among containers inside and outside the cluster, and
is often accomplished by deploying a driver on each node.

`calico_ipv4pool`

:   IPv4 network in CIDR format.
    It refers to the IPv4 address pool used by the Calico network plugin for allocating IP addresses to pods in Kubernetes clusters.
    **Default value**: 10.100.0.0/16.

`service_cluster_ip_range`

:   IPv4 network in CIDR format.
    Defines the range of IP addresses allocated for Kubernetes services within clusters managed by Magnum.
    These IP addresses are used to expose and connect services.
    **Default value**: 10.254.0.0/16

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

* `octavia_provider`

   The Octavia provider to configure for the load balancers created by the cluster.

   Default value: Octavia default

* `octavia_lb_algorithm`

   The Octavia load balancer algorithm to configure for the load balancers
   created by the cluster (options are `ROUND_ROBIN`, `LEAST_CONNECTIONS`,
   `SOURCE_IP` & `SOURCE_IP_PORT`).

   It's important to note that the OVN provider supports only the `SOURCE_IP_PORT`
   driver as part of it's [limitations](https://docs.openstack.org/ovn-octavia-provider/latest/admin/driver.html).

   Default value (`amphora` provider): `ROUND_ROBIN`
   Default value (`ovn` provider): `SOURCE_IP_PORT`

* `octavia_lb_healthcheck`

   The Octavia Load Balancer members can be monitored with health monitor.
   This must be enabled when externalTrafficPolicy is set to `Local`.

   Default value: `True`

## Container Networking Interface (CNI)

### Calico

* `calico_tag`

   The version of the Calico container image to use when bootstrapping the
   cluster.
   Please note, that in case of selecting version out of the supported range,
   you will need to supply a manifest for it.

   Default value: `v3.31.3`
   Supported values: `v3.24.2`, `v3.25.2`, `v3.26.5`, `v3.27.4`, `v3.28.2`, `v3.29.0`, `v3.29.2`, `v3.29.3`, `v3.30.0`, `v3.30.1`, `v3.30.2`, `v3.31.3`

### Cilium

* `cilium_hubble_ui_enabled`

   Enable the Cilium Hubble UI for network observability. When enabled, both
   the Hubble Relay and Hubble UI components are deployed, allowing users to
   visualize network flows and service dependencies in their clusters.

   Default value: `false`

## Container Storage Interface (CSI)

### Cinder

* `cinder_csi_plugin_tag`

   The version of the Cinder CSI container image to use when bootstrapping the
   cluster.

   Default value: Automatically detected based on `kube_tag` label.

### Manila

* `manila_csi_plugin_tag`

   The version of the Manila CSI container image to use when bootstrapping the
   cluster.

   Default value: Automatically detected based on `kube_tag` label.

* `manila_csi_share_network_id`

   Manila [share network](https://wiki.openstack.org/wiki/Manila/Concepts#share_network) ID.

   Default value: `None`

## Kubernetes

* `api_server_cert_sans`

   Specify the additional Subject Alternative Names (SANs) for the Kubernetes API Server,
   separated by commas.

* `api_server_tls_cipher_suites`

   Specify the list of TLS cipher suites to use for the Kubernetes API server,
   separated by commas.  If not specified, the default list of cipher suites
   will be used using the [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/#server=go&config=intermediate).

   Default value: `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305`

* `auto_healing_enabled`

   Enable auto-healing for the cluster.  This will automatically replace failed
   nodes in the cluster with new nodes (after 5 minutes of not being ready)
   and stops further remediation if more than 40% of the cluster is unhealthy.

   Default value: `true`

* `auto_scaling_enabled`

   Enable auto-scaling for the cluster.  This will automatically scale the
   cluster up and down based on the number of pods running in the cluster.

   Default value: `false`

* `kubelet_tls_cipher_suites`

   Specify the list of TLS cipher suites to use in communication between the
   kubelet and applications, separated by commas.  If not specified, the
   default list of cipher suites will be used.

   Default value: `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305`

* `kube_tag`

   The version of Kubernetes to use.

   Default value: `v1.25.3`

* `master_lb_floating_ip_enabled`

   Attach a floating IP to the load balancer that fronts the Kubernetes API
   servers.  In order to disable this, you must be running the
   `magnum-cluster-api-proxy` service on all your Neutron network nodes.

   Default value: `true`

## OIDC

* `oidc_issuer_url`

   The URL of the OpenID issuer, only HTTPS scheme will be accepted. If set, it
   will be used to verify the OIDC JSON Web Token (JWT).

   Default value: ``

* `oidc_client_id`

   The client ID for the OpenID Connect client, must be set if `oidc_issuer_url`
   is set.

   Default value: ``

* `oidc_username_claim`

   The OpenID claim to use as the user name.

   Default value: `sub`

* `oidc_username_prefix`

   If provided, all usernames will be prefixed with this value. If not provided,
   username claims other than 'email' are prefixed by the issuer URL to avoid
   clashes. To skip any prefixing, use the default value.

   Default value: `-`

* `oidc_groups_claim`

   If provided, the name of a custom OpenID Connect claim for specifying user
   groups. The claim value is expected to be a string or array of strings.

   Default value: ``

* `oidc_groups_prefix`

   If provided, all groups will be prefixed with this value to prevent conflicts
   with other authentication strategies.

   Default value: ``

## OpenStack

* `fixed_subnet_cidr`

   The CIDR of the fixed subnet to use for the cluster.

   Default value: `10.0.0.0/24`

* `different_failure_domain`

    Enable [failure domain filter](https://github.com/vexxhost/nova-scheduler-filters).
    This spreads cluster nodes across different failure domains.

   Default value: `false`

* `server_group_policies`

    Specify the server group policies. A server group is created for each cluster node group.
    Nodes in a node group are scheduled following the policies specified for the corresponding
    server group.

    Controlplane node group uses the cluster label while other node groups use labels at each
    node group level. If node group label is not configured, cluster level label is applied.

   Default value: `soft-anti-affinity`

## TODO

availability_zone
dns_cluster_domain
calico_ipv4pool
