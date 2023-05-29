# Copyright (c) 2023 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import re
import string
import textwrap

import pykube
import shortuuid
import yaml
from magnum import objects as magnum_objects
from magnum.common import context, exception, octavia
from magnum.common.keystone import KeystoneClientV3
from oslo_log import log as logging
from oslo_serialization import base64
from oslo_utils import strutils
from tenacity import retry, retry_if_exception_type

from magnum_cluster_api import clients, image_utils, images, objects

LOG = logging.getLogger(__name__)


def get_or_generate_cluster_api_cloud_config_secret_name(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> str:
    return f"{get_or_generate_cluster_api_name(api, cluster)}-cloud-config"


def get_or_generate_cluster_api_name(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> str:
    if cluster.stack_id is None:
        cluster.stack_id = generate_cluster_api_name(api)
        cluster.save()
    return cluster.stack_id


@retry(retry=retry_if_exception_type(exception.Conflict))
def generate_cluster_api_name(
    api: pykube.HTTPClient,
) -> str:
    alphabet = string.ascii_lowercase + string.digits
    su = shortuuid.ShortUUID(alphabet=alphabet)

    name = "kube-%s" % (su.random(length=5))
    if cluster_exists(api, name):
        raise exception.Conflict("Generated name already exists")
    return name


def cluster_exists(api: pykube.HTTPClient, name: str) -> bool:
    try:
        objects.Cluster.objects(api, namespace="magnum-system").get(name=name)
        return True
    except pykube.exceptions.ObjectDoesNotExist:
        return False


def generate_cloud_controller_manager_config(
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
) -> str:
    """
    Generate coniguration for openstack-cloud-controller-manager if it does
    already exist.
    """
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
        tls-insecure={"false" if cloud_config["clouds"]["default"]["verify"] else "true"}
        """
    )


def generate_manila_csi_cloud_config(
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
) -> str:
    """
    Generate coniguration of Openstack authentication  for manila csi
    """
    data = pykube.Secret.objects(api, namespace="magnum-system").get_by_name(
        get_or_generate_cluster_api_cloud_config_secret_name(api, cluster)
    )
    clouds_yaml = base64.decode_as_text(data.obj["data"]["clouds.yaml"])
    cloud_config = yaml.safe_load(clouds_yaml)

    return {
        "os-authURL": cloud_config["clouds"]["default"]["auth"]["auth_url"],
        "os-region": cloud_config["clouds"]["default"]["region_name"],
        "os-applicationCredentialID": cloud_config["clouds"]["default"]["auth"][
            "application_credential_id"
        ],
        "os-applicationCredentialSecret": cloud_config["clouds"]["default"]["auth"][
            "application_credential_secret"
        ],
        "os-TLSInsecure": "false"
        if cloud_config["clouds"]["default"]["verify"]
        else "true",
    }


def get_kube_tag(cluster: magnum_objects.Cluster) -> str:
    return get_cluster_label(cluster, "kube_tag", "v1.25.3")


def get_auto_scaling_enabled(cluster: magnum_objects.Cluster) -> bool:
    return get_cluster_label_as_bool(cluster, "auto_scaling_enabled", False)


def get_cluster_container_infra_prefix(cluster: magnum_objects.Cluster) -> str:
    return get_cluster_label(
        cluster,
        "container_infra_prefix",
        "quay.io/vexxhost",
    )


def get_cluster_floating_ip_disabled(cluster: magnum_objects.Cluster) -> bool:
    return not get_cluster_label_as_bool(cluster, "master_lb_floating_ip_enabled", True)


def generate_containerd_config(
    cluster: magnum_objects.Cluster,
):
    image_repository = get_cluster_container_infra_prefix(cluster)
    sandbox_image = image_utils.get_image(images.PAUSE, image_repository)

    return textwrap.dedent(
        """\
        # Use config version 2 to enable new configuration fields.
        # Config file is parsed as version 1 by default.
        version = 2

        imports = ["/etc/containerd/conf.d/*.toml"]

        [plugins]
        [plugins."io.containerd.grpc.v1.cri"]
            sandbox_image = "{sandbox_image}"
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
            runtime_type = "io.containerd.runc.v2"
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
            SystemdCgroup = true
        """
    ).format(sandbox_image=sandbox_image)


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
    return node_group.min_node_count


def get_node_group_max_node_count(
    context: context.RequestContext,
    node_group: magnum_objects.NodeGroup,
) -> int:
    if node_group.max_node_count is None:
        return get_node_group_label_as_int(
            context,
            node_group,
            "max_node_count",
            get_node_group_min_node_count(node_group) + 1,
        )
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


def is_cinder_enabled():
    """Check if Cinder service is deployed in the cloud."""

    admin_context = context.make_admin_context()
    keystone = KeystoneClientV3(admin_context)

    try:
        cinder_svc = keystone.client.services.list(type="volumev3")
    except Exception:
        LOG.exception("Failed to list services")
        raise exception.ServicesListFailed()

    # Always assume there is only one load balancing service configured.
    if cinder_svc and cinder_svc[0].enabled:
        return True

    LOG.info("There is no volumev3 service enabled in the cloud.")
    return False


def is_manila_enabled():
    """Check if Manila service is deployed in the cloud."""

    admin_context = context.make_admin_context()
    keystone = KeystoneClientV3(admin_context)

    try:
        manila_svc = keystone.client.services.list(type="sharev2")
    except Exception:
        LOG.exception("Failed to list services")
        raise exception.ServicesListFailed()

    if manila_svc and manila_svc[0].enabled:
        return True

    LOG.info("There is no sharev2 service enabled in the cloud.")
    return False


def is_cinder_csi_enabled(cluster: magnum_objects.Cluster) -> bool:
    return (
        get_cluster_label_as_bool(cluster, "cinder_csi_enabled", True)
        and is_cinder_enabled()
    )


def is_manila_csi_enabled(cluster: magnum_objects.Cluster) -> bool:
    return (
        get_cluster_label_as_bool(cluster, "manila_csi_enabled", True)
        and is_manila_enabled()
    )
