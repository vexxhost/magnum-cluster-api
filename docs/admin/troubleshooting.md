# Troubleshooting

## Useful commands

### Tracking cluster progress using `clusterctl`

If you'd like to track the progress of a specific cluster from the `clusterctl`
perspective, you can run the following command to find out the `stack_id` of the
cluster and then use `clusterctl describe` to get the status of the cluster:

```
$ export CLUSTER_ID=$(openstack coe cluster show <cluster-name> -f value -c stack_id)
$ watch -cn1 'clusterctl describe cluster -n magnum-system $CLUSTER_ID --grouping=false --color'
```

## Cluster stuck in `CREATE_IN_PROGRESS` state

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
    $ kubectl -n magnum-system describe openstackmachines -l cluster.x-k8s.io/control-plane=,cluster.x-k8s.io/cluster-name=<stack-id>
    ```

    From the output, you will need to look at the `Status` field and see if
    any of the conditions are `False`.  If they are, you will need to look at
    the `Message` field to see what the error is.

## Cluster stuck in `DELETE_IN_PROGRESS` state

### Project deleted

If you have a case where a project has been deleted from OpenStack but the
cluster was not deleted, you will not be able to delete it even as an admin
user.   You will find log messages such as the following which will indicate
that the project is missing:

```
E0705 17:11:00.333902       1 controller.go:326] "Reconciler error" err=<providerClient authentication err: Resource not found: [POST https://cloud.atmosphere.dev/v3/auth/tokens], error message: {"error":{"code":404,"message":"Could not find project: 1dfcc1f4399948baac7a83a6607f693c.","title":"Not Found"}}
```

In order to work around this issue, you will need to create a new project,
go into the database and update the `id` of the new project to match the
`project_id` of the cluster.

!!! warning

    It is possible to corrupt the database if you do not know what you are
    doing.  Please make sure you have a backup of the database before

1.  Create a new project in OpenStack:

    ```
    $ export NEW_PROJECT_ID=$(openstack project create cleanup-project -f value -c id)
    ```

2.  Get the existing `project_id` of the cluster:

    ```
    $ export CURRENT_PROJECT_ID=$(openstack coe cluster show <cluster-name> -f value -c project_id)
    ```

3.  Update the `id` of the project in Keystone to match the `project_id` of
    the cluster:

    ```
    $ mysql -B -N -u root -p -e "update project set id='$CURRENT_PROJECT_ID' where id='$NEW_PROJECT_ID';" keystone
    ```

    If you're using Atmosphere, you can run the following:

    ```
    $ kubectl -n openstack exec -it sts/percona-xtradb-pxc -- mysql -hlocalhost -uroot -p$(kubectl -n openstack get secret/percona-xtradb -ojson | jq -r '.data.root' | base64 --decode) -e "update project set id='$CURRENT_PROJECT_ID' where id='$NEW_PROJECT_ID';" keystone
    ```

4.  Verify that the project now exists under the new `id`:

    ```
    $ openstack project show $CURRENT_PROJECT_ID
    ```

5.  Give access to your current admin user to the new project:

    ```
    $ openstack role add --user $OS_USERNAME --project $CURRENT_PROJECT_ID member
    ```

6.  Switch to the context of that user

    ```
    $ export OS_PROJECT_ID=$CURRENT_PROJECT_ID
    ```

7.  Create a new set of application credentials and update the existing
    `cloud-config` secret for the cluster

    ```
    $ export CAPI_CLUSTER_NAME=$(openstack coe cluster show tst1-useg-k8s-1 -f value -c stack_id)
    $ export EXISTING_APPCRED_ID=$(kubectl -n magnum-system get secret/$CAPI_CLUSTER_NAME-cloud-config -ojson | jq -r '.data."clouds.yaml"' | base64 --decode | grep application_credential_id | awk '{print $2}')
    $ export EXISTING_APPCRED_SECRET=$(kubectl -n magnum-system get secret/$CAPI_CLUSTER_NAME-cloud-config -ojson | jq -r '.data."clouds.yaml"' | base64 --decode | grep application_credential_secret | awk '{print $2}')
    $ export NEW_APPCRED_ID=$(openstack application credential create --secret $EXISTING_APPCRED_SECRET $CAPI_CLUSTER_NAME-cleanup -f value -c id)
    $  > /tmp/clouds.yaml
    $ kubectl -n magnum-system patch secret/$CAPI_CLUSTER_NAME-cloud-config -p '{"data":{"clouds.yaml":"'$(kubectl -n magnum-system get secret/$CAPI_CLUSTER_NAME-cloud-config -ojson | jq -r '.data."clouds.yaml"' | base64 --decode | sed "s/$EXISTING_APPCRED_ID/$NEW_APPCRED_ID/" | base64 --wrap=0)'"}}'
    ```

At this point, the cluster should start progressing on the deletion process, you
can verify this by running:

```
$ kubectl -n capo-system logs deploy/capo-controller-manager -f
```

Once the cluster is gone, you can clean up the project:

```
$ unset OS_PROJECT_ID
$ openstack project delete $CURRENT_PROJECT_ID
```
