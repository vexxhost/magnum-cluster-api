import shutil
import subprocess

import click

from magnum_cluster_api import image_utils

IMAGES = [
    "docker.io/calico/cni:v3.24.2",
    "docker.io/calico/kube-controllers:v3.24.2",
    "docker.io/calico/node:v3.24.2",
    "docker.io/k8scloudprovider/cinder-csi-plugin:v1.25.3",
    "docker.io/k8scloudprovider/openstack-cloud-controller-manager:v1.25.3",
    "k8s.gcr.io/coredns/coredns:v1.8.6",
    "k8s.gcr.io/coredns/coredns:v1.9.3",
    "k8s.gcr.io/etcd:3.5.1-0",
    "k8s.gcr.io/etcd:3.5.3-0",
    "k8s.gcr.io/etcd:3.5.3-0",
    "k8s.gcr.io/etcd:3.5.4-0",
    "k8s.gcr.io/kube-apiserver:v1.23.13",
    "k8s.gcr.io/kube-apiserver:v1.24.7",
    "k8s.gcr.io/kube-apiserver:v1.24.7",
    "k8s.gcr.io/kube-apiserver:v1.25.3",
    "k8s.gcr.io/kube-controller-manager:v1.23.13",
    "k8s.gcr.io/kube-controller-manager:v1.24.7",
    "k8s.gcr.io/kube-controller-manager:v1.24.7",
    "k8s.gcr.io/kube-controller-manager:v1.25.3",
    "k8s.gcr.io/kube-proxy:v1.23.13",
    "k8s.gcr.io/kube-proxy:v1.24.7",
    "k8s.gcr.io/kube-proxy:v1.24.7",
    "k8s.gcr.io/kube-proxy:v1.25.3",
    "k8s.gcr.io/kube-scheduler:v1.23.13",
    "k8s.gcr.io/kube-scheduler:v1.24.7",
    "k8s.gcr.io/kube-scheduler:v1.24.7",
    "k8s.gcr.io/kube-scheduler:v1.25.3",
    "k8s.gcr.io/pause:3.6",
    "k8s.gcr.io/pause:3.7",
    "k8s.gcr.io/pause:3.8",
    "k8s.gcr.io/sig-storage/csi-attacher:v3.4.0",
    "k8s.gcr.io/sig-storage/csi-node-driver-registrar:v2.5.1",
    "k8s.gcr.io/sig-storage/csi-provisioner:v3.1.0",
    "k8s.gcr.io/sig-storage/csi-resizer:v1.4.0",
    "k8s.gcr.io/sig-storage/csi-snapshotter:v6.0.1",
    "k8s.gcr.io/sig-storage/livenessprobe:v2.7.0",
]


@click.command()
@click.option(
    "--repository",
    show_default=True,
    default="quay.io/vexxhost",
    help="Target image repository",
)
def main(repository):
    """
    Load images into a remote registry for `container_infra_prefix` usage.
    """
    crane_path = shutil.which("crane")

    if crane_path is None:
        raise click.UsageError(
            """Crane is not installed. Please install it before running this command:
             https://github.com/google/go-containerregistry/blob/main/cmd/crane/README.md#installation"""
        )

    for image in IMAGES:
        src = image
        dst = image_utils.get_image(image, repository)

        try:
            subprocess.run(
                [crane_path, "copy", src, dst], capture_output=True, check=True
            )
        except subprocess.CalledProcessError as e:
            if "401 Unauthorized" in e.stderr.decode():
                click.echo(
                    "Authentication failed. Please ensure you're logged in via Crane.",
                    err=True,
                )
                return

            click.echo(e.stderr.decode(), err=True)
            return

        click.echo(f"Successfully mirrored {src} to {dst}")
