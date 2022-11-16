import re
import textwrap

import pykube
import shortuuid
import yaml
from magnum import objects as magnum_objects
from magnum.common import context, exception, octavia
from oslo_serialization import base64
from oslo_utils import strutils
from tenacity import retry, retry_if_exception_type

from magnum_cluster_api import clients, objects


def get_or_generate_cluster_api_cloud_config_secret_name(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> str:
    return f"{get_or_generate_cluster_api_name(api, cluster)}-cloud-config"


def get_or_generate_cluster_api_name(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> str:
    if cluster.stack_id is None:
        cluster.stack_id = generate_cluster_api_name(api, cluster)
        cluster.save()
    return cluster.stack_id


@retry(retry=retry_if_exception_type(exception.Conflict))
def generate_cluster_api_name(
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
) -> str:
    name = f"{cluster.name}-{shortuuid.uuid()[:10].lower()}".replace(".", "-")
    if (
        objects.Cluster.objects(api)
        .filter(namespace="magnum-system")
        .get_or_none(name=name)
        is not None
    ):
        raise exception.Conflict("Generated name already exists")
    return name


def generate_cloud_controller_manager_config(
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
) -> str:
    """
    Generate coniguration for openstack-cloud-controller-manager if it does
    already exist.
    """
    api = clients.get_pykube_api()

    data = pykube.Secret.objects(api, namespace="magnum-system").get_by_name(
        get_or_generate_cluster_api_cloud_config_secret_name(api, cluster)
    )
    clouds_yaml = base64.decode_as_text(data.obj["data"]["clouds.yaml"])
    cloud_config = yaml.safe_load(clouds_yaml)

    return textwrap.dedent(
        f"""\
        [Global]
        auth-url={cloud_config["clouds"]["default"]["auth"]["auth_url"]}
        region={cloud_config["clouds"]["default"]["region_name"]}
        application-credential-id={cloud_config["clouds"]["default"]["auth"]["application_credential_id"]}
        application-credential-secret={cloud_config["clouds"]["default"]["auth"]["application_credential_secret"]}
        """
    )


def get_node_group_label(
    context: context.RequestContext,
    node_group: magnum_objects.NodeGroup,
    key: str,
    default: str,
) -> str:
    cluster = magnum_objects.Cluster.get_by_uuid(context, node_group.cluster_id)
    return node_group.labels.get(key, get_cluster_label(cluster, key, default))


def get_node_group_min_node_count(
    node_group: magnum_objects.NodeGroup,
    default=1,
) -> int:
    if node_group.min_node_count == 0:
        return default
    else:
        return node_group.min_node_count


def get_node_group_max_node_count(
    node_group: magnum_objects.NodeGroup,
) -> int:
    if node_group.max_node_count is None:
        return get_node_group_min_node_count(node_group) + 1
    else:
        return node_group.max_node_count


def get_cluster_label(cluster: magnum_objects.Cluster, key: str, default: str) -> str:
    return cluster.labels.get(
        key, get_cluster_template_label(cluster.cluster_template, key, default)
    )


def get_cluster_template_label(
    cluster_template: magnum_objects.ClusterTemplate, key: str, default: str
) -> str:
    return cluster_template.labels.get(key, default)


def get_node_group_label_as_int(
    context: context.RequestContext,
    node_group: magnum_objects.NodeGroup,
    key: str,
    default: int,
) -> int:
    value = get_node_group_label(context, node_group, key, default)
    return strutils.validate_integer(value, key)


def get_cluster_label_as_int(
    cluster: magnum_objects.Cluster, key: str, default: int
) -> int:
    value = get_cluster_label(cluster, key, default)
    return strutils.validate_integer(value, key)


def get_cluster_label_as_bool(
    cluster: magnum_objects.Cluster, key: str, default: bool
) -> bool:
    value = get_cluster_label(cluster, key, default)
    return strutils.bool_from_string(value, strict=True)


def get_image(name: str, repository: str = None):
    """
    Get the image name from the target registry given a full image name.
    """

    if repository is None:
        return repository

    new_image_name = name
    if name.startswith("docker.io/calico"):
        new_image_name = name.replace("docker.io/calico/", f"{repository}/calico-")
    if name.startswith("docker.io/k8scloudprovider"):
        new_image_name = name.replace("docker.io/k8scloudprovider", repository)
    if name.startswith("k8s.gcr.io/sig-storage"):
        new_image_name = name.replace("k8s.gcr.io/sig-storage", repository)
    if new_image_name.startswith(f"{repository}/livenessprobe"):
        return new_image_name.replace("livenessprobe", "csi-livenessprobe")
    if new_image_name.startswith("k8s.gcr.io/coredns"):
        return new_image_name.replace("k8s.gcr.io/coredns", repository)
    if (
        new_image_name.startswith("k8s.gcr.io/etcd")
        or new_image_name.startswith("k8s.gcr.io/kube-")
        or new_image_name.startswith("k8s.gcr.io/pause")
    ):
        return new_image_name.replace("k8s.gcr.io", repository)

    assert new_image_name.startswith(repository) is True
    return new_image_name


def update_manifest_images(
    cluster: magnum_objects.Cluster, file, repository=None, replacements=[]
):
    with open(file) as fd:
        data = fd.read()

    docs = []
    for doc in yaml.safe_load_all(data):
        # Fix container image paths
        if doc["kind"] in ("DaemonSet", "Deployment"):
            for container in doc["spec"]["template"]["spec"]["containers"]:
                for src, dst in replacements:
                    container["image"] = container["image"].replace(src, dst)
                if repository:
                    container["image"] = get_image(container["image"], repository)

        # Fix CCM cluster-name
        if (
            doc["kind"] == "DaemonSet"
            and doc["metadata"]["name"] == "openstack-cloud-controller-manager"
        ):
            for env in doc["spec"]["template"]["spec"]["containers"][0]["env"]:
                if env["name"] == "CLUSTER_NAME":
                    env["value"] = cluster.uuid

        docs.append(doc)

    return yaml.safe_dump_all(docs, default_flow_style=False)


def delete_loadbalancers(ctx, cluster):
    # NOTE(mnaser): This code is duplicated from magnum.common.octavia
    #               since the original code is very Heat-specific.
    pattern = r"Kubernetes .+ from cluster %s" % cluster.uuid

    admin_ctx = context.get_admin_context()
    admin_clients = clients.get_openstack_api(admin_ctx)
    user_clients = clients.get_openstack_api(ctx)

    candidates = set()

    try:
        octavia_admin_client = admin_clients.octavia()
        octavia_client = user_clients.octavia()

        # Get load balancers created for service/ingress
        lbs = octavia_client.load_balancer_list().get("loadbalancers", [])
        lbs = [lb for lb in lbs if re.match(pattern, lb["description"])]
        deleted = octavia._delete_loadbalancers(
            ctx, lbs, cluster, octavia_admin_client, remove_fip=True
        )
        candidates.update(deleted)

        if not candidates:
            return

        octavia.wait_for_lb_deleted(octavia_client, candidates)
    except Exception as e:
        raise exception.PreDeletionFailed(cluster_uuid=cluster.uuid, msg=str(e))
