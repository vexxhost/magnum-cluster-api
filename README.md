# `magnum-cluster-api`

## Testing & Development

In order to be able to test and develop the `magnum-cluster-api` project, you
will need to have an existing Magnum deployment.  You can use the following
steps to be able to test and develop the project.

1. Start up a DevStack environment with all Cluster API dependencies

   ```bash
   ./hack/stack.sh
   ```

1. Upload an image to use with Magnum

   ```bash
   TODO
   ```

1. Create a cluster template that uses the Cluster API driver

   ```bash
   openstack coe cluster template create \
     --image 2fe53e0a-4f77-4608-beb8-12fdc595c03b \
     --external-network public \
     --dns-nameserver 8.8.8.8 \
     --master-lb-enabled \
     --flavor m1.medium \
     --master-flavor m1.medium \
     --docker-volume-size 5 \
     --network-driver calico \
     --docker-storage-driver overlay2 \
     --coe kubernetes \
     k8s-cluster-template-capi
   ```

1. Spin up a new cluster using the Cluster API driver

   ```bash
   openstack coe cluster create \
     --cluster-template k8s-cluster-template-capi \
     --master-count 3 \
     --node-count 2 \
     k8s-cluster
   ```

1. Once the cluster reaches `CREATE_COMPLETE` state, you can interact with it:

   ```bash
   eval $(openstack coe cluster config k8s-cluster)
   ```

## TODO

- audit all labels + options to make sure it works
- cluster resize
- cluster upgrade
- [autohealing](https://cluster-api.sigs.k8s.io/tasks/automated-machine-management/healthchecking.html)
  with `auto_healing_enabled`
- [autoscaling](https://cluster-api.sigs.k8s.io/tasks/automated-machine-management/autoscaling.html)
- boot from volume
- custom image location
- ingress
- k8s_keystone_auth_tag
- kube_dashboard_enabled
- monitoring (maybe?)
