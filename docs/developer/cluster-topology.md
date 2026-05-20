# Cluster Topology

The Cluster API driver for Magnum makes use of the Cluster topology feature of the Cluster API project.  This allows it to delegate all of the work around building resources such as the `OpenStackCluster`, `MachineDeployments` and everything else managed entire by the Cluster API instead of the driver creating all of these resources.

In order to do this, the driver creates a [`ClusterClass`](https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass) resource which is called `magnum-v{VERSION}` where `{VERSION}` is the current version of the driver because of the following reasons:

- This allows us to have multiple different versions of the `ClusterClass` because it is an immutable resource.
- This prevents causing a rollout of existing clusters should a change happen to the underlying `ClusterClass`.

It's important to note that there are only _one_ scenarios where the `spec.topology.class` for a given `Cluster` will be modified and this will be when a cluster upgrade is done.  This is because there is an expectation by the user that a rolling restart operation will occur if a cluster upgrade is requested.  No other action should be allowed to change the `spec.topology.class` of a `Cluster`.

For users, it's important to keep in mind that if they want to use a newer `ClusterClass` in order to make sure of a new feature available in a newer `ClusterClass`, they can simply do an upgrade within Magnum to the same cluster template and it will actually force an update of the `spec.topology.class`, which might then naturally cause a full rollout to occur.

## Kubelet configuration profiles

Kubelet configuration profiles are operator-defined management-cluster
resources.  They let users select a reviewed kubelet tuning mode without
exposing an arbitrary `KubeletConfiguration` JSON passthrough in Magnum labels.

Profiles are defined in the `mcapi-kubelet-config-profiles` ConfigMap in the
management cluster namespace, normally `magnum-system`:

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

  profile-bm-gpu-layout: |
    nodegroups:
      gpu-workers:
        kubeletConfigProfile: profile-gpu
```

Each kubelet profile value is a YAML object.  Supported kubelet profile fields
are `cpuManagerPolicy`, `topologyManagerPolicy`, `reservedSystemCPUs`, and
`maxPods`.  Layout profiles use a `nodegroups` object that maps nodegroup names
to `kubeletConfigProfile` references.

Users select the cluster default profile with the `kubelet_config_profile`
label.  Users select nodegroup-specific layout with
`kubelet_nodegroup_config_profile_set`.  Unknown profile names, invalid layout
profiles, and layout profiles that reference unknown kubelet profiles must be
rejected during cluster validation and in the kubelet config rendering path.

The cluster default profile renders as the `kubeletConfig` Cluster topology
variable.  Layout profile entries render as MachineDeployment-level
`kubeletConfig` variable overrides, so a worker pool such as `gpu-workers` can
receive a different kubelet configuration from the cluster default.
