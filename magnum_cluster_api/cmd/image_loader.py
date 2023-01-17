import shutil

import click
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging

from magnum_cluster_api import image_utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
DOMAIN = "magnum-cluster-api"

logging.register_options(CONF)
logging.setup(CONF, DOMAIN)

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
            "Crane is not installed. Please install it before running this command."
        )

    seen = []
    for image in IMAGES:
        if image in seen:
            continue

        src = image
        dst = image_utils.get_image(image, repository)

        LOG.debug(f"Starting to mirror {src} to {dst}")

        try:
            processutils.execute(
                crane_path,
                "copy",
                src,
                dst,
            )
        except processutils.ProcessExecutionError as e:
            if "401 Unauthorized" in e.stderr:
                LOG.error(
                    "Authentication failed. Please ensure you're logged in via Crane"
                )
                return

            raise

        seen.append(image)
        LOG.info(f"Successfully mirrored {src} to {dst}")
