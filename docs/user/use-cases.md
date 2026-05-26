# Use Cases

## GPU and NUMA-aware kubelet tuning

Baremetal and GPU clusters often need kubelet CPU and topology settings so
workloads can use predictable CPU pinning and NUMA-aware scheduling behavior.
Use an operator-defined `profile-gpu` configuration profile to select reviewed
kubelet and bootstrap configuration.

The cloud operator must define the profile in the management cluster before
users can select it.  Profiles are operator-managed entries in the
`mcapi-config-profiles` ConfigMap, normally in the `magnum-system`
namespace:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcapi-config-profiles
  namespace: magnum-system
data:
  profile-gpu: |
    kubeletConfig:
      cpuManagerPolicy: static
      cpuManagerPolicyOptions:
        full-pcpus-only: "true"
      memoryManagerPolicy: Static
      topologyManagerPolicy: single-numa-node
      topologyManagerScope: pod
      reservedSystemCPUs: 0-1
      maxPods: 250
    files:
      - path: /etc/gpu-init.sh
        permissions: "0755"
        content: |
          #!/bin/bash
          modprobe nvidia || true
    preKubeadmCommands:
      - bash /etc/gpu-init.sh
```

```bash
openstack coe cluster create bm-gpu \
  --cluster-template k8s-bm \
  --labels config_profile=profile-gpu
```

This renders a kubeadm `KubeletConfiguration` patch similar to:

```yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cpuManagerPolicy: static
cpuManagerPolicyOptions:
  full-pcpus-only: "true"
memoryManagerPolicy: Static
topologyManagerPolicy: single-numa-node
topologyManagerScope: pod
reservedSystemCPUs: 0-1
maxPods: 250
```

Configuration profiles are defined by the cloud operator in the management cluster.
Magnum users select a supported profile with `config_profile`; they do
not create new profiles through cluster labels.  If the ConfigMap is missing or
an unknown profile name is passed, cluster validation fails.

To change kubelet configuration after cluster creation, use Magnum cluster
upgrade to a cluster template that selects a different profile:

```bash
openstack coe cluster template create k8s-bm-gpu-v2 \
  ...same base template options... \
  --labels config_profile=profile-gpu

openstack coe cluster upgrade bm-gpu k8s-bm-gpu-v2
```

The driver does not accept arbitrary kubelet JSON configuration through labels.
It also does not expose individual kubelet fields or cloud-init snippets as
Magnum labels.  Cloud operators define named profiles in the profile ConfigMap,
and users select those named profiles.

## Nodegroup-specific kubelet tuning

Some baremetal clusters need special kubelet settings only for a subset of
worker pools.  For example, a `gpu-workers` nodegroup may need static CPU
manager and NUMA-aware topology settings, while default workers should keep the
standard kubelet configuration.

Use `config_profile` for the cluster default and
`nodegroup_config_profile_set` for an operator-defined nodegroup layout:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcapi-config-profiles
  namespace: magnum-system
data:
  profile-standard: |
    kubeletConfig:
      maxPods: 110

  profile-gpu: |
    kubeletConfig:
      cpuManagerPolicy: static
      cpuManagerPolicyOptions:
        full-pcpus-only: "true"
      memoryManagerPolicy: Static
      topologyManagerPolicy: single-numa-node
      topologyManagerScope: pod
      reservedSystemCPUs: 0-1
      maxPods: 250

  profile-bm-gpu-layout: |
    nodegroups:
      gpu-workers:
        profile: profile-gpu
```

```bash
openstack coe cluster create bm-gpu \
  --cluster-template k8s-bm \
  --labels config_profile=profile-standard \
  --labels nodegroup_config_profile_set=profile-bm-gpu-layout
```

The cluster default profile applies to the control plane and worker
MachineDeployments not mentioned by the layout.  The layout profile renders a
MachineDeployment-level `configProfile` override for `gpu-workers`.
