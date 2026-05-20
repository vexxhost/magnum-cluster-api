# Use Cases

## GPU and NUMA-aware kubelet tuning

Baremetal and GPU clusters often need kubelet CPU and topology settings so
workloads can use predictable CPU pinning and NUMA-aware scheduling behavior.
Use an operator-defined `profile-gpu` kubelet configuration profile to select a
reviewed kubelet configuration.

The cloud operator must define the profile in the management cluster before
users can select it.  Profiles are operator-managed entries in the
`mcapi-kubelet-config-profiles` ConfigMap, normally in the `magnum-system`
namespace:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcapi-kubelet-config-profiles
  namespace: magnum-system
data:
  profile-gpu: |
    cpuManagerPolicy: static
    topologyManagerPolicy: single-numa-node
    reservedSystemCPUs: 0-1
    maxPods: 250
```

```bash
openstack coe cluster create bm-gpu \
  --cluster-template k8s-bm \
  --labels kubelet_config_profile=profile-gpu
```

This renders a kubeadm `KubeletConfiguration` patch similar to:

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cpuManagerPolicy: static
topologyManagerPolicy: single-numa-node
reservedSystemCPUs: 0-1
maxPods: 250
```

Kubelet profiles are defined by the cloud operator in the management cluster.
Magnum users select a supported profile with `kubelet_config_profile`; they do
not create new profiles through cluster labels.  If the ConfigMap is missing or
an unknown profile name is passed, cluster validation fails.

To change kubelet configuration after cluster creation, use Magnum cluster
upgrade to a cluster template that selects a different profile:

```bash
openstack coe cluster template create k8s-bm-gpu-v2 \
  ...same base template options... \
  --labels kubelet_config_profile=profile-gpu

openstack coe cluster upgrade bm-gpu k8s-bm-gpu-v2
```

The driver does not accept arbitrary kubelet JSON configuration through labels.
It also does not expose individual kubelet fields as Magnum labels.  If another
kubelet field needs to be exposed, the cloud operator should add it to a named
profile.

## Nodegroup-specific kubelet tuning

Some baremetal clusters need special kubelet settings only for a subset of
worker pools.  For example, a `gpu-workers` nodegroup may need static CPU
manager and NUMA-aware topology settings, while default workers should keep the
standard kubelet configuration.

Use `kubelet_config_profile` for the cluster default and
`kubelet_nodegroup_config_profile_set` for an operator-defined nodegroup layout:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcapi-kubelet-config-profiles
  namespace: magnum-system
data:
  profile-standard: |
    maxPods: 110

  profile-gpu: |
    cpuManagerPolicy: static
    topologyManagerPolicy: single-numa-node
    reservedSystemCPUs: 0-1
    maxPods: 250

  profile-bm-gpu-layout: |
    nodegroups:
      gpu-workers:
        kubeletConfigProfile: profile-gpu
```

```bash
openstack coe cluster create bm-gpu \
  --cluster-template k8s-bm \
  --labels kubelet_config_profile=profile-standard \
  --labels kubelet_nodegroup_config_profile_set=profile-bm-gpu-layout
```

The cluster default profile applies to the control plane and worker
MachineDeployments not mentioned by the layout.  The layout profile renders a
MachineDeployment-level `kubeletConfig` override for `gpu-workers`.
