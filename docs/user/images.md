# Images

## Operating System Images

The Cluster API driver for Magnum relies on specific OpenStack images containing
all necessary dependencies for deploying Kubernetes clusters. These images are
pre-configured with Kubernetes binaries, container runtimes, networking
components, and other required software.

The images used by the Cluster API driver for Magnum are built using the
[`kubernetes-sigs/image-builder`](https://github.com/kubernetes-sigs/image-builder)
project. This project provides a comprehensive and flexible framework for
constructing Kubernetes-specific images.

### Building Images

In order to simplify the process of building images, the Cluster API driver for
Magnum provides a small Python utility which wraps the `image-builder` project.

To build the images, run the following command:

```console
$ pip install magnum-cluster-api
$ magnum-cluster-api-image-builder --version v1.26.2
```

In the example above, this command will build the images for Kubernetes version
`v1.26.2`. The `--version` flag is optional and defaults to `v1.26.2`.
