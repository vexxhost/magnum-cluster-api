# Getting Started

## Cluster Operations

### Creating

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
