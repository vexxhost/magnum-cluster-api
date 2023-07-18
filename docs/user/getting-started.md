# Getting Started

## Cluster Operations

### Creating

You can use a few different methods to create a Kubernetes cluster with the
Cluster API driver for Magnum.  We cover a few different methods in this
section.

#### OpenStack CLI

The OpenStack CLI is the easiest way to create a Kubernetes cluster.  You can
use the `openstack coe cluster create` command to create a Kubernetes cluster
with the Cluster API driver for Magnum.

Before you get started, you'll have to make sure that you have the cluster
templates you want to use available in your environment.  You can create them
using the OpenStack CLI:

```bash
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
```

Once you've got a cluster template, you can create a cluster using the OpenStack
CLI:

```console
$ openstack coe cluster create --cluster-template <cluster-template-name> <cluster-name>
```

You'll be able to view teh status of the deployment using the OpenStack CLI:

```console
$ openstack coe cluster show <cluster-name>
```

#### Deployment Speed

The Cluster API driver for Magnum is designed to be fast.  It is capable of
deploying a Kubernetes cluster in under 5 minutes.  However, there are several
factors that can slow down the deployment process:

* **Operating system image size**
  The average size of the operating system image is around 4 GB.  The image
  needs to be downloaded to each node before deploying the cluster, and the
  download speed depends on the network connection. The compute service caches
  images locally, so the initial cluster deployment is slower than subsequent
  deployments.

* **Network connectivity**
  When the cluster goes up, it needs to pull all the container images from the
  container registry.  By default, it will pull all the images from the upstream
  registries.  If you have a slow network connection, you can use a local
  registry to speed up the deployment process and read more about pointing to
  it in the [Labels](labels.md#images) section.

!!! note

    [Atmosphere](https://github.com/vexxhost/atmosphere) deploys a local
    registry by default as well as includes several speed optimizations to
    improve the deployment speed down to 5 minutes.

### Upgrading

The Cluster API driver for Magnum supports upgrading Kubernetes clusters to any
minor release in the same series or one major release ahead.  The upgrade
process is performed in-place, meaning that the existing cluster is upgraded to
the new version without creating a new cluster in a rolling fashion.

!!! note

    You must have an operating system image for the new Kubernetes version
    available in Glance before upgrading the cluster.  See the [Images
    documentation](images.md) for more information.

In order to upgrade a cluster, you must have a cluster template pointing at the
image for the new Kubernetes version and the `kube_tag` label must be updated
to point at the new Kubernetes version.

Once you have this cluster template, you can trigger an upgrade by using the
OpenStack CLI:

```console
$ openstack coe cluster upgrade <cluster-name> <cluster-template-name>
```

### Node group role
Roles can be used to show the purpose of a node group, and multiple node groups can be given the same role if they share a common purpose.
Role information is available within Kubernetes as `node-role.kubernetes.io/ROLE_NAME` label on the nodes.
The label `node.cluster.x-k8s.io/nodegroup` is also available for selecting a specific node group.
