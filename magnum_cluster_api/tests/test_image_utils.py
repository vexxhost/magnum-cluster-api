import glob
import os
import uuid

import pkg_resources
import yaml

from magnum_cluster_api import image_utils


def test_update_manifest_images_for_calico():
    manifests_path = pkg_resources.resource_filename("magnum_cluster_api", "manifests")
    repository = "quay.io/test"

    cluster_uuid = str(uuid.uuid4())

    for manifest_file in glob.glob(os.path.join(manifests_path, "calico/*.yaml")):
        data = image_utils.update_manifest_images(
            cluster_uuid,
            manifest_file,
            repository=repository,
        )

        for doc in yaml.safe_load_all(data):
            if doc["kind"] in ("DaemonSet", "Deployment"):
                for init_container in doc["spec"]["template"]["spec"].get(
                    "initContainers", []
                ):
                    assert init_container["image"].startswith(repository)
                for container in doc["spec"]["template"]["spec"]["containers"]:
                    assert container["image"].startswith(repository)
