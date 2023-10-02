![Cluster API driver for Magnum](docs/static/logo.png?raw=true "Cluster API driver for Magnum")

The Cluster API driver for Magnum allows you to deploy fully conformant
Kubernetes cluster using the [Cluster API](https://cluster-api.sigs.k8s.io/)
project which are fully integrated with the OpenStack cluster they are running
on.

For more information, please refer to the following resources:

* **Documentation**: https://vexxhost.github.io/magnum-cluster-api/
* **Community**: [`#magnum-cluster-api`](https://kubernetes.slack.com/archives/C05Q8TDTK6Z) channel
  on the Kubernetes Slack. If you are new to Kubernetes Slack workspace,
  [Join the Kubernetes Slack workspace](https://slack.kubernetes.io/) first.

## Images

The images are built and published to an object storage bucket hosted at the
[VEXXHOST](https://vexxhost.com) public cloud.  These images are built and
published for the latest stable release of Kubernetes.

### Pre-built images

You can find the pre-built images for the latest stable release of Kubernetes
at the following URL:

#### Ubuntu 22.04

* [v1.23.17](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.23.17.qcow2)
* [v1.24.16](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.24.16.qcow2)
* [v1.25.12](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.25.12.qcow2)
* [v1.26.7](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.26.7.qcow2)
* [v1.27.4](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/ubuntu-2204-kube-v1.27.4.qcow2)

#### Flatcar

* [v1.24.16](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/flatcar-kube-v1.24.16.qcow2)
* [v1.25.12](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/flatcar-kube-v1.25.12.qcow2)
* [v1.26.7](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/flatcar-kube-v1.26.7.qcow2)
* [v1.27.4](https://object-storage.public.mtl1.vexxhost.net/swift/v1/a91f106f55e64246babde7402c21b87a/magnum-capi/flatcar-kube-v1.27.4.qcow2)

### Building images

The Cluster API driver for Magnum provides a tool in order to build images, you
can use it by installing the `magnum-cluster-api` package and running the
the following command:

```bash
magnum-cluster-api-image-builder
```

## Testing & Development

For more information on how to test, develop and contribute to the Cluster API
driver for Magnum, refer to the [developer guide](https://vexxhost.github.io/magnum-cluster-api/developer/testing-and-development/).
