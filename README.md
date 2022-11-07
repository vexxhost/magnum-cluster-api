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

1. Upload an image to use with Magnum and create cluster templates

   ```bash
   pushd /tmp
   source /opt/stack/openrc
   for version in v1.23.13 v1.24.7 v1.25.3; do \
      curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2004-${version}.qcow2; \
      openstack image create ubuntu-2004-${version} --disk-format=qcow2 --container-format=bare --property os_distro=ubuntu-focal --file=ubuntu-2004-${version}.qcow2; \
      openstack coe cluster template create \
         --image $(openstack image show ubuntu-2004-${version} -c id -f value) \
         --external-network public \
         --dns-nameserver 8.8.8.8 \
         --master-lb-enabled \
         --master-flavor m1.medium \
         --flavor m1.medium \
         --network-driver calico \
         --docker-storage-driver overlay2 \
         --coe kubernetes \
         --label kube_tag=${version} \
         k8s-${version};
   done;
   popd /tmp
   ```

1. Spin up a new cluster using the Cluster API driver

   ```bash
   openstack coe cluster create \
     --cluster-template k8s-v1.25.3 \
     --master-count 3 \
     --node-count 2 \
     k8s-v1.25.3
   ```

1. Once the cluster reaches `CREATE_COMPLETE` state, you can interact with it:

   ```bash
   eval $(openstack coe cluster config k8s-cluster)
   ```
