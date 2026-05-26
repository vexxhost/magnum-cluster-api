# Cluster Topology

The Cluster API driver for Magnum makes use of the Cluster topology feature of the Cluster API project.  This allows it to delegate all of the work around building resources such as the `OpenStackCluster`, `MachineDeployments` and everything else managed entire by the Cluster API instead of the driver creating all of these resources.

In order to do this, the driver creates a [`ClusterClass`](https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass) resource which is called `magnum-v{VERSION}` where `{VERSION}` is the current version of the driver because of the following reasons:

- This allows us to have multiple different versions of the `ClusterClass` because it is an immutable resource.
- This prevents causing a rollout of existing clusters should a change happen to the underlying `ClusterClass`.

It's important to note that there are only _one_ scenarios where the `spec.topology.class` for a given `Cluster` will be modified and this will be when a cluster upgrade is done.  This is because there is an expectation by the user that a rolling restart operation will occur if a cluster upgrade is requested.  No other action should be allowed to change the `spec.topology.class` of a `Cluster`.

For users, it's important to keep in mind that if they want to use a newer `ClusterClass` in order to make sure of a new feature available in a newer `ClusterClass`, they can simply do an upgrade within Magnum to the same cluster template and it will actually force an update of the `spec.topology.class`, which might then naturally cause a full rollout to occur.

## Configuration profiles

Configuration profiles are operator-defined management-cluster resources.  They
let users select reviewed node bootstrap changes without exposing arbitrary
cloud-init or kubeadm configuration in Magnum labels.

Profiles are defined in the `mcapi-config-profiles` ConfigMap in the management
cluster namespace, normally `magnum-system`:

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

  profile-bm-gpu-layout: |
    nodegroups:
      gpu-workers:
        profile: profile-gpu
```

Each profile value is a YAML object.  `kubeletConfig` contains a kubeadm
`KubeletConfiguration` fragment; Magnum renders `apiVersion` and `kind`, so the
fragment must not set those fields.  `files`, `preKubeadmCommands`, and
`postKubeadmCommands` are rendered into CAPI kubeadm config fields for the
control plane and workers.

Layout profiles use a `nodegroups` object that maps nodegroup names to `profile`
references.

Users select the cluster default profile with the `config_profile` label.  Users
select nodegroup-specific layout with `nodegroup_config_profile_set`.  Unknown
profile names, invalid layout profiles, and layout profiles that reference
unknown profiles must be rejected during cluster validation and rendering.

The cluster default profile renders as the `configProfile` Cluster topology
variable.  Layout profile entries render as MachineDeployment-level
`configProfile` variable overrides, so a worker pool such as `gpu-workers` can
receive different files, commands, and kubelet configuration from the cluster
default.
