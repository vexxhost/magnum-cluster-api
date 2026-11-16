# CNI Upgrade Guide

This guide provides step-by-step instructions for upgrading the Container
Network Interface (CNI) plugin within your Magnum-provisioned Kubernetes
cluster. It covers both **Cilium** and **Calico** upgrade procedures.

!!! warning "Read before proceeding"

    CNI upgrades affect pod-to-pod networking. While both Cilium and Calico
    support rolling upgrades with minimal disruption, it is strongly recommended
    to:

    - **Test the upgrade in a non-production cluster first.**
    - **Ensure you have a recent etcd backup** (if applicable).
    - **Drain and cordon nodes** if you want to be extra cautious.
    - **Review the upstream release notes** for breaking changes specific to
      your version jump.

## Prerequisites

Before starting any CNI upgrade, ensure you have the following:

1. **`kubectl` access** to the target Magnum cluster with cluster-admin
   privileges.
2. **Helm v3.10+** installed locally.
3. **Network connectivity** to pull updated container images (or a local
   registry mirror configured via the `container_infra_prefix` label).
4. Verify the current CNI and version running in your cluster:

    ```bash
    # For Cilium
    kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium -o wide
    cilium_pod=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium-agent -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                 kubectl get pods -n kube-system -l k8s-app=cilium -o jsonpath='{.items[0].metadata.name}')
    kubectl exec -n kube-system "$cilium_pod" -- cilium version

    # For Calico
    kubectl get pods -n kube-system -l k8s-app=calico-node -o wide
    kubectl get pods -n kube-system -l k8s-app=calico-node \
      -o jsonpath='{.items[0].spec.containers[0].image}'
    ```

---

## Cilium Upgrade

Cilium is deployed in Magnum clusters via a Helm chart (vendored at version
**1.15.3**). The recommended upgrade path is to use Helm directly against the
running cluster.

### Supported upgrade path

Cilium supports upgrading **one minor version at a time** (e.g. 1.15 → 1.16).
Skipping minor versions is **not** supported. Always consult the
[Cilium Upgrade Guide](https://docs.cilium.io/en/stable/operations/upgrade/)
for your target version.

### Step 1 — Add the Cilium Helm repository

```bash
helm repo add cilium https://helm.cilium.io/
helm repo update
```

### Step 2 — Identify your current configuration

The Magnum Cluster API driver configures Cilium with specific values. Before
upgrading, extract the running configuration so you can preserve it:

```bash
# Get the current Helm release values (if installed as a Helm release)
helm get values cilium -n kube-system -o yaml > cilium-current-values.yaml 2>/dev/null

# If Cilium was deployed via ClusterResourceSet (not a Helm release),
# inspect the running DaemonSet for image tags and key settings:
kubectl get daemonset cilium -n kube-system -o yaml | grep "image:"
```

### Step 3 — Prepare the values file

Use the provided [`cilium-upgrade-values.yaml`](#cilium-values-file) below as a
starting point. This file contains the settings that match how Magnum deploys
Cilium, adjusted for the upgrade target version.

**Review and adjust the following before applying:**

| Parameter | Description | Action |
|-----------|-------------|--------|
| `image.tag` | Cilium agent image tag | Set to your target version (e.g. `v1.16.19`) |
| `operator.image.tag` | Cilium operator image tag | Must match the agent tag |
| `ipam.operator.clusterPoolIPv4PodCIDRList` | Pod CIDR | Must match your cluster's pod CIDR (default: `10.100.0.0/16`) |
| `hubble.relay.enabled` | Hubble relay | Set to `true` if you use Hubble |
| `hubble.ui.enabled` | Hubble UI | Set to `true` if you use the Hubble UI |

!!! note "Image registry"

    If your cluster uses a private registry (set via the `container_infra_prefix`
    Magnum label), update the `image.repository` fields accordingly. The Magnum
    driver remaps `cilium/` to `cilium-` in the image name (e.g.,
    `myregistry.example.com/cilium-cilium`).

### Step 4 — Pre-flight check (recommended)

Cilium provides a pre-flight check to validate that the upgrade can proceed
safely:

```bash
helm install cilium-preflight cilium/cilium \
  --namespace kube-system \
  --version <TARGET_CHART_VERSION> \
  --set preflight.enabled=true \
  --set agent=false \
  --set operator.enabled=false
```

Wait for the pre-flight DaemonSet to be ready on all nodes:

```bash
kubectl rollout status daemonset/cilium-pre-flight-check -n kube-system --timeout=300s
```

Then remove the pre-flight check:

```bash
helm uninstall cilium-preflight -n kube-system
```

### Step 5 — Perform the upgrade

Since Magnum deploys Cilium via a ClusterResourceSet (rendered `helm template`
output applied as raw manifests), it is **not** installed as a Helm release. You
have two options:

#### Option A — Install as a Helm release (recommended for ongoing management)

This converts the Cilium deployment from raw manifests to a managed Helm
release, making future upgrades simpler.

!!! important "Both labels AND annotations are required"

    Helm requires two things to adopt existing resources: the
    `meta.helm.sh/release-name` and `meta.helm.sh/release-namespace`
    **annotations**, plus the `app.kubernetes.io/managed-by: Helm` **label**.
    You must also include **Hubble** resources (secrets, services) that may not
    carry a `cilium` label.

```bash
# Step A1: Annotate AND label Cilium CRDs
kubectl get crd -o name | grep cilium | xargs -I {} sh -c '
  kubectl annotate {} meta.helm.sh/release-name=cilium meta.helm.sh/release-namespace=kube-system --overwrite
  kubectl label {} app.kubernetes.io/managed-by=Helm --overwrite
'

# Step A2: Annotate AND label all namespaced Cilium resources (by label selectors)
for selector in "app.kubernetes.io/part-of=cilium" "k8s-app=cilium"; do
  kubectl get all,sa,cm,secret,role,rolebinding \
    -n kube-system -l "$selector" -o name 2>/dev/null | \
    xargs -I {} sh -c '
      kubectl annotate -n kube-system {} meta.helm.sh/release-name=cilium meta.helm.sh/release-namespace=kube-system --overwrite 2>/dev/null
      kubectl label -n kube-system {} app.kubernetes.io/managed-by=Helm --overwrite 2>/dev/null
    '
done

# Step A3: Annotate AND label cluster-scoped RBAC (by name, since Magnum-deployed
# resources may not have Cilium label selectors)
for r in clusterrole/cilium clusterrole/cilium-operator \
         clusterrolebinding/cilium clusterrolebinding/cilium-operator; do
  kubectl annotate "$r" \
    meta.helm.sh/release-name=cilium meta.helm.sh/release-namespace=kube-system --overwrite
  kubectl label "$r" \
    app.kubernetes.io/managed-by=Helm --overwrite
done

# Step A4: Annotate AND label Hubble secrets and SA (not covered by Cilium labels).
# Do NOT suppress errors here — if a resource is missing the Helm install will fail.
for r in secret/cilium-ca secret/hubble-server-certs service/hubble-peer \
         serviceaccount/cilium serviceaccount/cilium-operator configmap/cilium-config; do
  kubectl annotate -n kube-system "$r" \
    meta.helm.sh/release-name=cilium meta.helm.sh/release-namespace=kube-system --overwrite
  kubectl label -n kube-system "$r" \
    app.kubernetes.io/managed-by=Helm --overwrite
done

# Step A5: Install/upgrade using Helm with the values file
helm upgrade --install cilium cilium/cilium \
  --namespace kube-system \
  --version <TARGET_CHART_VERSION> \
  --values cilium-upgrade-values.yaml
```

#### Option B — Template and apply manually

If you prefer to keep using raw manifests (matching the Magnum deployment
model), this is the simpler option since it does not require annotating
existing resources:

```bash
helm template cilium cilium/cilium \
  --namespace kube-system \
  --version <TARGET_CHART_VERSION> \
  --values cilium-upgrade-values.yaml > cilium-manifests.yaml

kubectl apply --server-side --force-conflicts -f cilium-manifests.yaml
```

!!! note "No annotation steps needed"

    Unlike Option A, this approach does not require adopting resources into a
    Helm release. The `--server-side --force-conflicts` flags handle ownership
    conflicts automatically. Future upgrades can be performed by regenerating
    the template with the new version and reapplying.

### Step 6 — Verify the upgrade

```bash
# Check that all Cilium pods are running the new version
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium -o wide
kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium-operator -o wide

# Verify connectivity
cilium_pod=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=cilium-agent -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             kubectl get pods -n kube-system -l k8s-app=cilium -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n kube-system "$cilium_pod" -- cilium status
kubectl exec -n kube-system "$cilium_pod" -- cilium version

# Run a connectivity test (optional but recommended)
kubectl exec -n kube-system "$cilium_pod" -- cilium connectivity test 2>/dev/null || \
  echo "Use 'cilium-cli connectivity test' if you have cilium-cli installed"
```

### Step 7 — Prevent Magnum from reverting the upgrade

!!! important

    The Magnum Cluster API driver manages Cilium via a **ClusterResourceSet**
    with `ApplyOnce` strategy. This means the CNI manifests are applied only
    at cluster creation and are **not** reapplied during subsequent cluster
    updates or reconciliations. However, to avoid any risk of version mismatch
    in the future:

    1. **Coordinate with your platform operator** to update the `cilium_tag`
       label in the cluster template to match your upgraded version.
    2. **Do not run `openstack coe cluster update`** on CNI-related labels
       unless the platform operator has already updated `cilium_tag` to your
       target version.
    3. If you adopted Cilium as a Helm release (Option A), Helm's ownership
       annotations protect against overwrites. If a conflict does occur,
       delete the legacy ClusterResourceSet from the management cluster:

        ```bash
        # Find and delete the legacy CRS (named after the cluster UUID)
        kubectl get clusterresourceset -n magnum-system
        kubectl delete clusterresourceset <cluster-uuid> -n magnum-system
        ```

---

### Cilium values file

Download [`cilium-upgrade-values.yaml`](cilium-upgrade-values.yaml) and adjust
for your environment. The file contains all the Magnum-compatible defaults with
clear comments indicating which values you must change for your target version
and cluster configuration.

---

## Calico Upgrade

Calico is deployed in Magnum clusters via raw upstream manifests (not a Helm
chart). The current default version is **v3.31.3**. The recommended upgrade
approach is to use the **Calico Operator with Helm**, which provides a cleaner
upgrade path than raw manifests.

### Supported upgrade path

Calico supports upgrading **across minor versions** within the v3.x series, but
always review the
[Calico Release Notes](https://docs.tigera.io/calico/latest/release-notes/)
for your target version. Major version jumps (e.g., v3.28 → v3.31) are
generally supported but should be tested first.

### Method 1 — Manifest-based upgrade (matches Magnum deployment model)

This method replaces the existing Calico manifests with the new version,
matching how Magnum originally deployed Calico.

#### Step 1 — Identify the current version

```bash
kubectl get pods -n kube-system -l k8s-app=calico-node -o jsonpath='{.items[0].spec.containers[0].image}'
```

#### Step 2 — Download the target version manifest

```bash
TARGET_VERSION="v3.31.3"  # Change to your target version
curl -LO "https://raw.githubusercontent.com/projectcalico/calico/${TARGET_VERSION}/manifests/calico.yaml"
```

#### Step 3 — Review and adjust the manifest

Before applying, verify that the pod CIDR in the manifest matches your cluster
configuration. The Magnum default is `10.100.0.0/16`:

```bash
# Check the CALICO_IPV4POOL_CIDR value in the downloaded manifest
grep -A2 "CALICO_IPV4POOL_CIDR" calico.yaml
```

If the CIDR needs to be changed (it should match your cluster's
`calico_ipv4pool` label):

```bash
# Check your cluster's current pod CIDR
kubectl get ippool -o yaml 2>/dev/null || \
  kubectl get ippools.crd.projectcalico.org -o yaml 2>/dev/null || \
  kubectl get cm -n kube-system calico-config -o yaml | grep -i cidr
```

!!! note "Pod CIDR auto-detection"

    Recent Calico manifests (v3.28+) have the `CALICO_IPV4POOL_CIDR` variable
    **commented out** by default. In this case, Calico auto-detects the CIDR
    from the existing IPPool resources. If upgrading from Magnum's default
    configuration, auto-detection works correctly — you typically do **not**
    need to uncomment or set this variable.

Edit the manifest to ensure `CALICO_IPV4POOL_CIDR` matches your pod CIDR
if it is uncommented.

#### Step 4 — Apply the upgraded manifest

!!! important "Use `--server-side --force-conflicts`"

    The Calico manifest will conflict with field managers on existing resources.
    You **must** use server-side apply with `--force-conflicts` to avoid errors.

```bash
kubectl apply --server-side --force-conflicts -f calico.yaml
```

#### Step 5 — Verify the upgrade

```bash
# Watch the rollout
kubectl rollout status daemonset/calico-node -n kube-system --timeout=300s
kubectl rollout status deployment/calico-kube-controllers -n kube-system --timeout=300s

# Verify the new version
kubectl get pods -n kube-system -l k8s-app=calico-node -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'
```

---

### Method 2 — Migrate to Calico Operator with Helm (recommended for ongoing management)

The Calico Operator provides a more robust lifecycle management experience.
This method migrates from the raw-manifest deployment to an operator-managed
deployment.

!!! warning

    Migrating from manifest-based Calico to the operator is a more involved
    process. See the
    [Tigera operator migration guide](https://docs.tigera.io/calico/latest/operations/operator-migration)
    for full details. The steps below provide a simplified workflow.

!!! note "Namespace migration"

    After installing the Tigera operator, Calico pods are automatically
    migrated from `kube-system` to the `calico-system` namespace. The
    operator handles this migration transparently — do not manually delete
    pods in `kube-system` during the process.

!!! info "Version jump support"

    Although the Tigera documentation states that operator migration is
    only supported from a matching manifest version, testing has confirmed
    that migrating directly from older versions (e.g., v3.27.4 → v3.31.4)
    works successfully. The operator auto-detects existing settings and
    performs the upgrade as part of the migration.

#### Step 1 — Add the Calico Helm repository

```bash
helm repo add projectcalico https://docs.tigera.io/calico/charts
helm repo update
```

#### Step 2 — Prepare the values file

Use the provided [`calico-upgrade-values.yaml`](#calico-values-file) file as a
starting point. Review and adjust the settings for your environment.

#### Step 3 — Install the Tigera operator

```bash
helm upgrade --install calico projectcalico/tigera-operator \
  --namespace tigera-operator \
  --create-namespace \
  --version <TARGET_CHART_VERSION> \
  --values calico-upgrade-values.yaml
```

#### Step 4 — Verify the upgrade

The migration typically takes 3–5 minutes. During this time the operator
rolling-updates calico-node pods and moves them from `kube-system` to
`calico-system`.

```bash
# Check operator status — all components should show AVAILABLE=True
kubectl get tigerastatus

# Verify calico-node pods are running in calico-system (not kube-system)
kubectl get pods -n calico-system -l k8s-app=calico-node -o wide
kubectl get pods -n calico-system -l k8s-app=calico-kube-controllers -o wide

# Confirm kube-system calico pods have been cleaned up
kubectl get pods -n kube-system -l k8s-app=calico-node 2>&1

# Check version
kubectl exec -n calico-system daemonset/calico-node -- calico-node -v 2>/dev/null | head -1
```

!!! note "Expected warnings during migration"

    You may see operator log messages such as "Cannot update an IP pool not
    owned by the operator" during migration. These are expected and resolve
    automatically as the operator takes ownership of existing resources.

---

### Calico values file

For the **manifest-based upgrade** (Method 1), no Helm values file is needed —
you apply the upstream manifest directly.

For the **Helm-based migration** (Method 2), download
[`calico-upgrade-values.yaml`](calico-upgrade-values.yaml) and adjust for your
environment. The file contains the Tigera Operator configuration with
Magnum-compatible defaults.

---

## Post-upgrade verification (both CNIs)

After upgrading either CNI, verify end-to-end cluster networking:

```bash
# 1. Create a test namespace
kubectl create namespace cni-upgrade-test

# 2. Deploy two test pods
kubectl run test-server --image=nginx --namespace=cni-upgrade-test --labels="app=test-server"
kubectl run test-client --image=busybox --namespace=cni-upgrade-test --command -- sleep 3600

# 3. Wait for pods to be ready
kubectl wait --for=condition=Ready pod/test-server -n cni-upgrade-test --timeout=120s
kubectl wait --for=condition=Ready pod/test-client -n cni-upgrade-test --timeout=120s

# 4. Expose the server
kubectl expose pod test-server --port=80 --namespace=cni-upgrade-test

# 5. Wait for endpoints to propagate
sleep 10

# 6. Test pod-to-pod connectivity via service DNS
kubectl exec -n cni-upgrade-test test-client -- wget -qO- --timeout=10 http://test-server.cni-upgrade-test.svc.cluster.local

# 7. Clean up
kubectl delete namespace cni-upgrade-test
```

## Preventing Magnum from reverting CNI changes

!!! important

    The Magnum Cluster API driver manages CNI via a **ClusterResourceSet** with
    `ApplyOnce` strategy, meaning the CNI manifests are applied only at cluster
    creation and are **not** automatically reapplied during updates or
    reconciliations. Your manually upgraded CNI will not be overwritten by
    normal cluster operations.

    However, to keep the cluster metadata consistent:

    1. Coordinate with your platform operator to update the default CNI version
       in the Magnum cluster template or cluster labels (`cilium_tag` / `calico_tag`).
    2. Avoid running `openstack coe cluster update` on CNI-related labels
       unless the operator has already updated the CNI version.
    3. If a conflict does occur (e.g. due to a future behavior change), you
       can delete the legacy ClusterResourceSet from the management cluster
       to stop it from competing with your upgraded CNI:

        ```bash
        kubectl get clusterresourceset -n magnum-system
        kubectl delete clusterresourceset <cluster-uuid> -n magnum-system
        ```

## Troubleshooting

### Cilium operator `ErrImagePull` with "operator-generic-generic"

If the operator pod shows `ErrImagePull` with an image name like
`quay.io/cilium/operator-generic-generic`, the `operator.image.repository`
value is incorrect. The Cilium Helm chart automatically appends the platform
suffix (e.g., `-generic`) to the operator image name. Set:

```yaml
operator:
  image:
    repository: quay.io/cilium/operator  # NOT "operator-generic"
```

### Helm cannot adopt existing resources

If `helm upgrade --install` fails with "invalid ownership metadata", you need
to add **both** annotations and labels to all existing Cilium and Hubble
resources:

```bash
# Required annotation
meta.helm.sh/release-name=cilium
meta.helm.sh/release-namespace=kube-system
# Required label
app.kubernetes.io/managed-by=Helm
```

Don't forget resources like `secret/cilium-ca`, `secret/hubble-server-certs`,
and `service/hubble-peer` which may not match `cilium` label selectors.

### Pods stuck in `ContainerCreating` after upgrade

This usually indicates the CNI binary or configuration on the node is not ready.

```bash
# Check CNI pod logs
kubectl logs -n kube-system -l k8s-app=cilium --tail=50  # For Cilium
kubectl logs -n kube-system -l k8s-app=calico-node --tail=50  # For Calico (Method 1)
kubectl logs -n calico-system -l k8s-app=calico-node --tail=50  # For Calico (Method 2 / operator)

# Check node conditions
kubectl get nodes -o wide
kubectl describe node <node-name> | grep -A5 "Conditions"
```

### Network policies not enforced after upgrade

```bash
# For Cilium - check policy enforcement
kubectl exec -n kube-system -l k8s-app=cilium -- cilium policy get

# For Calico - check Felix status (use calico-system if using the operator)
kubectl exec -n kube-system -l k8s-app=calico-node -- calico-node -felix-live
kubectl exec -n calico-system -l k8s-app=calico-node -- calico-node -felix-live 2>/dev/null
```

### CRD version conflicts

If you see errors about CRD versions, you may need to update CRDs separately
before upgrading:

```bash
# For Cilium
helm template cilium cilium/cilium --version <TARGET_VERSION> --set preflight.enabled=true | kubectl apply -f -

# For Calico (manifest method)
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/<TARGET_VERSION>/manifests/crds.yaml
```
