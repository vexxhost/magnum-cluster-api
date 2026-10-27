# Kubelet serving certificates

By default, every kubelet serves its API (used for `kubectl logs`, `exec`,
`port-forward` and metrics) with a self-signed certificate, and the Kubernetes
API server connects to it without verifying who it's talking to.  Clusters
created with the `kubelet_serving_tls_enabled=true` label close that gap:

- Every kubelet requests a serving certificate signed by the cluster CA.
- The API server verifies that certificate before talking to a kubelet.
- [cluster-api-csr-approver](https://github.com/vexxhost/cluster-api-csr-approver)
  approves each request only when the names and IP addresses in it belong to
  the node that asked for them.

This page explains how the pieces fit together and what you need to do as a
cloud operator before users can turn the label on.

## How it works

When the label is set, the driver changes the cluster in two ways:

1. Every node gets a kubeadm patch file at
   `/etc/kubernetes/patches/kubeletconfiguration0+strategic.json` that sets
   `serverTLSBootstrap: true`, and kubeadm is pointed at that directory for
   `init` and `join`.  kubeadm applies it before the kubelet starts, on control
   plane and worker nodes alike, so no configuration is edited after the fact.
2. `kube-apiserver` runs with
   `--kubelet-certificate-authority=/etc/kubernetes/pki/ca.crt`, so it rejects
   any kubelet whose certificate isn't signed by the cluster CA.

Each kubelet then files a CertificateSigningRequest (CSR) with the
`kubernetes.io/kubelet-serving` signer.  Kubernetes deliberately never approves
these on its own, because something has to check that the requested names
really belong to the node.  The node can't be trusted to answer that itself,
since a kubelet can write its own `Node.status.addresses`.

cluster-api-csr-approver runs next to the Cluster API controllers in the
management cluster.  It watches pending kubelet serving CSRs in each workload
cluster through the Cluster API cluster cache, finds the Cluster API `Machine`
behind the requesting node, and approves the CSR only if:

- it was made by `system:node:<node>` and that node belongs to the Machine;
- the request has the subject, key usages and signer Kubernetes expects;
- every IP address in it is listed in the Machine's `status.addresses`;
- every DNS name in it is the node name or a hostname or DNS address of the
  Machine.

Machine addresses come from the Cluster API provider for OpenStack, which
copies them from the Nova server and its Neutron ports.  Fixed IPs, floating
IPs and additional networks all show up there, so they are approved, and a
node can never get a certificate for another node's address.  Certificate
renewals go through the same checks.  Nothing extra runs inside the workload
cluster.

## Installing the approver

The approver needs Cluster API v1.11 or later.  It is released as a clusterctl
add-on provider.  Add it to your `clusterctl.yaml`:

```yaml
providers:
  - name: csr-approver
    type: AddonProvider
    url: https://github.com/vexxhost/cluster-api-csr-approver/releases/latest/addon-components.yaml
```

Then install it.  This also works on a management cluster that already has
Cluster API installed:

```console
$ clusterctl init --addon csr-approver:v0.1.0
```

It runs as the `capi-csr-approver-controller-manager` Deployment in the
`capi-csr-approver-system` namespace.

If you deploy with [Atmosphere](https://github.com/vexxhost/atmosphere), the
`vexxhost.kubernetes.cluster_api` role installs it when it's listed in
`cluster_api_addon_providers`:

```yaml
cluster_api_addon_providers:
  - name: csr-approver
    version: 0.1.0
```

For environments without internet access, mirror
`ghcr.io/vexxhost/cluster-api-csr-approver` and override the registry in
`clusterctl.yaml`:

```yaml
images:
  addon-csr-approver:
    repository: registry.example.com/vexxhost
```

## Which clusters the approver handles

The driver puts exactly one of these labels on every Cluster API `Cluster` it
manages:

| Magnum label | Cluster API `Cluster` label |
|---|---|
| `kubelet_serving_tls_enabled=true` | `csr-approver.vexxhost.com/enabled: "true"` |
| `kubelet_serving_tls_enabled=false` or unset | `csr-approver.vexxhost.com/disabled: "true"` |

That works with both of the approver's documented selector settings:

- **Default** (`csr-approver.vexxhost.com/disabled!=true`): the approver
  handles every cluster except those labeled `disabled`.  Clusters without
  kubelet serving certificates are labeled `disabled`, so the approver doesn't
  connect to them.
- **Opt-in** (`csr-approver.vexxhost.com/enabled=true`): the approver handles
  only clusters labeled `enabled`.  This is the better choice when the
  management cluster only runs Magnum clusters, or when other clusters
  shouldn't be touched:

  ```console
  $ CSR_APPROVER_CLUSTER_SELECTOR=csr-approver.vexxhost.com/enabled=true \
      clusterctl init --addon csr-approver:v0.1.0
  ```

Clusters created before this change get their label the next time they're
upgraded.  Until then, an approver using the default selector connects to them
as well.  That's harmless because they never file kubelet serving CSRs.

If you use a custom selector, or run the approver with `--watch-filter`, make
sure it still matches clusters labeled `csr-approver.vexxhost.com/enabled`.
The driver can't check the selector for you.

## Approver settings

These are set once for the whole management cluster, as clusterctl variables
or in `clusterctl.yaml`:

| Variable | Default | Description |
|---|---|---|
| `CSR_APPROVER_CLUSTER_SELECTOR` | `csr-approver.vexxhost.com/disabled!=true` | Which clusters to handle, see above. |
| `CSR_APPROVER_DENY_INVALID` | `false` | Deny requests that fail the checks instead of leaving them pending. |
| `CSR_APPROVER_MAX_EXPIRATION` | `0s` (no limit) | Reject requests asking for a longer lifetime through `spec.expirationSeconds`. |
| `CSR_APPROVER_LOG_LEVEL` | `2` | Log verbosity. |

Leaving failed requests pending (the default) means an administrator can still
approve one by hand with `kubectl certificate approve`.  Turn on
`CSR_APPROVER_DENY_INVALID` if your policy requires an explicit decision on
every request.

## Checks in the driver

With `--kubelet-certificate-authority` set, a new control plane node only
becomes ready once its kubelet serving certificate is approved, because the
KubeadmControlPlane etcd health checks go through the kubelet.  Without a
running approver, the control plane would never come up and the operation would
hang until it timed out.

To avoid that, when a cluster has `kubelet_serving_tls_enabled=true`, the
driver checks for an available Deployment labeled
`cluster.x-k8s.io/provider=addon-csr-approver` before it:

- creates the cluster;
- resizes the cluster;
- upgrades the cluster, which replaces every node.

If none is found, the operation fails immediately with an error asking you to
install the approver.  Clusters without the label skip the check.

## Troubleshooting

A kubelet without an approved serving certificate has nothing to serve its API
with.  The usual symptoms are:

- `kubectl logs` or `kubectl exec` fails with `remote error: tls: internal error`;
- a new control plane node never becomes ready, so the cluster or upgrade stays
  `IN_PROGRESS`.

In the workload cluster, list the pending requests:

```console
$ kubectl get csr --field-selector spec.signerName=kubernetes.io/kubelet-serving
```

In the management cluster, the approver records why it didn't approve a
request as a `CSRNotApproved` event on the Machine, naming the address that
didn't match:

```console
$ kubectl -n magnum-system get events --field-selector reason=CSRNotApproved
$ kubectl -n capi-csr-approver-system logs deploy/capi-csr-approver-controller-manager
```

The approver also skips clusters that are paused, whose control plane isn't
initialized yet, or that don't match its selector.  It exposes
`capi_csr_approver_csr_total{result="approved|not_approved|denied"}` for
monitoring.

## Limitations

- The label can only be set when a cluster is created.  To use kubelet serving
  certificates on an existing cluster, create a new cluster with the label.
- Keep the approver installed for as long as any cluster uses the label.
  Kubelets renew their serving certificates before they expire, and renewals
  need approval too.
- The kubelet has to request only addresses the provider reports on the
  Machine.  On OpenStack, the cloud controller manager sets node addresses from
  the same Nova server, so they match.
