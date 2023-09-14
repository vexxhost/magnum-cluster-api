![Cluster API driver for Magnum](docs/static/logo.png?raw=true "Cluster API driver for Magnum")

The Cluster API driver for Magnum allows you to deploy fully conformant
Kubernetes cluster using the [Cluster API](https://cluster-api.sigs.k8s.io/)
project which are fully integrated with the OpenStack cluster they are running
on.
Here is the full [Documentation](https://vexxhost.github.io/magnum-cluster-api/).

## Community

If you have any questions and discussions about this Magnum Cluster API driver,
you can join the community:

* [`#magnum-cluster-api`](https://kubernetes.slack.com/archives/C05Q8TDTK6Z) channel
  on the Kubernetes Slack. If you are new to Kubernetes Slack workspace,
  [Join the Kubernetes Slack workspace](https://slack.kubernetes.io/) first.

## Images

The images are built and published to an object storage bucket hosted at the
[VEXXHOST](https://vexxhost.com) public cloud.  These images are built and
published for the latest stable release of Kubernetes.

### Pre-built images

You can find the pre-built images for the latest stable release of Kubernetes
at the following URL:

* [v1.23.17](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.23.17.qcow2)
* [v1.24.15](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.24.15.qcow2)
* [v1.25.11](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.25.11.qcow2)
* [v1.26.6](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.26.6.qcow2)
* [v1.27.3](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.27.3.qcow2)

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
   for version in v1.23.17 v1.24.15 v1.25.11 v1.26.6 v1.27.3; do \
      curl -LO https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-${version}.qcow2; \
      openstack image create ubuntu-2204-kube-${version} --disk-format=qcow2 --container-format=bare --property os_distro=ubuntu --file=ubuntu-2204-kube-${version}.qcow2; \
      openstack coe cluster template create \
         --image $(openstack image show ubuntu-2204-kube-${version} -c id -f value) \
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
   popd
   ```

1. Spin up a new cluster using the Cluster API driver

   ```bash
   openstack coe cluster create \
     --cluster-template k8s-v1.25.11 \
     --master-count 3 \
     --node-count 2 \
     k8s-v1.25.11
   ```

1. Once the cluster reaches `CREATE_COMPLETE` state, you can interact with it:

   ```bash
   eval $(openstack coe cluster config k8s-v1.25.11)
   ```
