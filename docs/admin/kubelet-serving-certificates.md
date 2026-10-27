# Kubelet serving certificate verification

By default, every kubelet serves its API (used for `kubectl logs`, `exec`,
`port-forward` and metrics) with a self-signed certificate, and the Kubernetes
API server connects to it without verifying it.  Clusters created with the
`kubelet_serving_cert_verification_enabled=true` label close that gap: every
kubelet gets a serving certificate signed by the cluster CA, and the API server
rejects any kubelet whose certificate it can't verify.  The legacy Heat driver
always worked this way.

## Requirements

Kubernetes never approves kubelet serving certificates on its own.  The driver
relies on [cluster-api-csr-approver][approver], which runs next to Cluster API
in the management cluster.  It approves a request only when every name and IP
address in it belongs to the OpenStack server behind that node, so floating
IPs and additional networks work, and a node can't get a certificate for
another node's address.  Nothing extra runs inside the workload cluster.

[Atmosphere](https://github.com/vexxhost/atmosphere) installs and enables the
approver by default, so there's nothing to do there.  For other deployments,
install it as described in its [README][approver-install] before users turn
the label on.

[approver]: https://github.com/vexxhost/cluster-api-csr-approver
[approver-install]: https://github.com/vexxhost/cluster-api-csr-approver#installing

## What the driver does

When the label is set, every node gets a kubeadm patch that sets
`serverTLSBootstrap: true` before the kubelet starts, and `kube-apiserver` runs
with `--kubelet-certificate-authority=/etc/kubernetes/pki/ca.crt`.

The driver also puts exactly one of these labels on the Cluster API `Cluster`,
so the approver handles the clusters that need it and leaves the others alone:

| Magnum label | Cluster API `Cluster` label |
|---|---|
| `kubelet_serving_cert_verification_enabled=true` | `csr-approver.vexxhost.com/enabled: "true"` |
| unset or `false` | `csr-approver.vexxhost.com/disabled: "true"` |

These match both the approver's default cluster selector and its opt-in one.
If you [configure][approver-config] a different selector, make sure it still
matches `csr-approver.vexxhost.com/enabled=true`.  Clusters created before this
change get their label the next time they're upgraded.

Once the API server verifies kubelets, a new control plane node only becomes
ready after its serving certificate is approved.  So before it creates, resizes
or upgrades a cluster with the label, the driver checks that an approver
Deployment (labeled `cluster.x-k8s.io/provider=addon-csr-approver`) is
available.  If not, the operation fails right away instead of hanging until it
times out.

[approver-config]: https://github.com/vexxhost/cluster-api-csr-approver#configuration

## Troubleshooting

A kubelet whose certificate hasn't been approved can't serve its API.
`kubectl logs` and `kubectl exec` fail with `remote error: tls: internal error`,
and a new control plane node never becomes ready.

To see the pending requests, run this in the workload cluster:

```console
$ kubectl get csr --field-selector spec.signerName=kubernetes.io/kubelet-serving
```

The approver records why it didn't approve a request as an event on the
matching Machine in the `magnum-system` namespace.  Its
[observability][approver-observability] section lists the events, logs and
metrics.

[approver-observability]: https://github.com/vexxhost/cluster-api-csr-approver#observability

## Limitations

- The label can only be set when a cluster is created.
- Keep the approver running for as long as any cluster uses the label.
  Kubelets renew their serving certificates before they expire, and renewals
  need approval too.
