# Cluster Topology

The Cluster API driver for Magnum makes use of the Cluster topology feature of the Cluster API project.  This allows it to delegate all of the work around building resources such as the `OpenStackCluster`, `MachineDeployments` and everything else managed entire by the Cluster API instead of the driver creating all of these resources.

In order to do this, the driver creates a [`ClusterClass`](https://cluster-api.sigs.k8s.io/tasks/experimental-features/cluster-class/write-clusterclass) resource which is called `magnum-v{VERSION}` where `{VERSION}` is the current version of the driver because of the following reasons:

- This allows us to have multiple different versions of the `ClusterClass` because it is an immutable resource.
- This prevents causing a rollout of existing clusters should a change happen to the underlying `ClusterClass`.

It's important to note that there are only _one_ scenarios where the `spec.topology.class` for a given `Cluster` will be modified and this will be when a cluster upgrade is done.  This is because there is an expectation by the user that a rolling restart operation will occur if a cluster upgrade is requested.  No other action should be allowed to change the `spec.topology.class` of a `Cluster`.

For users, it's important to keep in mind that if they want to use a newer `ClusterClass` in order to make sure of a new feature available in a newer `ClusterClass`, they can simply do an upgrade within Magnum to the same cluster template and it will actually force an update of the `spec.topology.class`, which might then naturally cause a full rollout to occur.
