# Images

## Operating System Images

The Cluster API driver for Magnum relies on specific OpenStack images containing
all necessary dependencies for deploying Kubernetes clusters. These images are
pre-configured with Kubernetes binaries, container runtimes, networking
components, and other required software.

### Building Images

The images used by the Cluster API driver for Magnum are built using the
[`vexxhost/capo-image-elements`](https://github.com/vexxhost/capo-image-elements)
project. This project provides a comprehensive and flexible framework for
constructing Kubernetes-specific images.

You can find pre-built images by this projet at
https://static.atmosphere.dev/artifacts/magnum-cluster-api/.

#### Deprecated legacy builder

The following is kept documented for the sakes of archiving however this
is a deprecated way that uses the `image-builder` project.  This is not
supported and the `magnum-cluster-api-image-builder` is slated to be
removed.

The images used by the Cluster API driver for Magnum are built using the
[`kubernetes-sigs/image-builder`](https://github.com/kubernetes-sigs/image-builder)
project. This project provides a comprehensive and flexible framework for
constructing Kubernetes-specific images.

In order to simplify the process of building images, the Cluster API driver for
Magnum provides a small Python utility which wraps the `image-builder` project.

To build the images, run the following command:

```console
$ pip install magnum-cluster-api
$ magnum-cluster-api-image-builder --version v1.26.2
```

In the example above, this command will build the images for Kubernetes version
`v1.26.2`. The `--version` flag is optional and defaults to `v1.26.2`.

