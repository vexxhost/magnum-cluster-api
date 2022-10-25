# `magnum-cluster-api`

## Images

The images are built and published to an object storage bucket hosted at the
[VEXXHOST](https://vexxhost.com) public cloud.  These images are built and
published for the latest stable release of Kubernetes.

### Pre-built images

You can find the pre-built images for the latest stable release of Kubernetes
at the following URL:

* [v1.23.13](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2004-v1.23.13.qcow2)
* [v1.24.7](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2004-v1.24.7.qcow2)
* [v1.25.3](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2004-v1.25.3.qcow2)

### Building images

The Cluster API driver for Magnum provides a tool in order to build images, you
can use it by installing the `magnum-cluster-api` package and running the
the following command:

```bash
magnum-cluster-api-image-builder
```

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

* audit all labels + options to make sure it works
* cluster resize
* cluster upgrade
* [autohealing](https://cluster-api.sigs.k8s.io/tasks/automated-machine-management/healthchecking.html)
  with `auto_healing_enabled`
* [autoscaling](https://cluster-api.sigs.k8s.io/tasks/automated-machine-management/autoscaling.html)
* boot from volume
* custom image location
* ingress
* k8s_keystone_auth_tag
* kube_dashboard_enabled
* monitoring (maybe?)
