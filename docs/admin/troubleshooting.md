# Troubleshooting

# Cluster stuck in `CREATE_IN_PROGRESS` state

With the Cluster API driver for Magnum, the cluster creation process is
performed by the Cluster API for OpenStack.  Due to the logic of how the
controller managers work, the process of creating a cluster is performed in
multiple steps and if a step fails, it will keep retrying until it succeeds.

Unlike the legacy Heat driver, the Cluster API driver for Magnum does not
move the state of the cluster to `CREATE_FAILED` if a step fails.  Instead,
it will keep the cluster in `CREATE_IN_PROGRESS` state until the cluster is
successfully created or the cluster is deleted.

If you are experiencing issues with the cluster being stuck in `CREATE_IN_PROGRESS`
state, you can follow the steps below to troubleshoot the issue:

1.  Check the `Cluster` name from the `stack_id` field in Magnum:

    ```
    $ openstack coe cluster show <cluster-name> -f value -c stack_id
    ```

2.  Check if the `Cluster` exists in the Kuberentes cluster using the `stack_id`:

    ```
    $ kubectl -n magnum-system get clusters <stack-id>
    ```

    !!! note
   
        If the cluster exists and it is in `Provisioned` state, you can skip to
        step 3.

3.  You will need to lookup the `OpenStackCluster` for the `Cluster`:

    ```
    $ kubectl -n magnum-system get openstackclusters -l cluster.x-k8s.io/cluster-name=<stack-id>
    ```

    !!! note

        If the `OpenStackCluster` shows `true` for `READY`, you can skip to
        step 4.

4.  You will have to look at the `KubeadmControlPlane` for
    the `OpenStackCluster`:

    ```
    $ kubectl -n magnum-system get kubeadmcontrolplanes -l cluster.x-k8s.io/cluster-name=<stack-id>
    ```

5.  If the number of `READY` nodes does not match the number of `REPLICAS`,
    you will need to investigate if the instances are going up by looking at
    the `OpenStackMachine` for the `KubeadmControlPlane`:

    ```
    $ kubectl -n magnum-system descrube openstackmachines -l cluster.x-k8s.io/control-plane=,cluster.x-k8s.io/cluster-name=<stack-id>
    ```

    From the output, you will need to look at the `Status` field and see if
    any of the conditions are `False`.  If they are, you will need to look at
    the `Message` field to see what the error is.
