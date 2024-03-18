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

from __future__ import annotations

import json
import re
import string
import textwrap

import pykube
import shortuuid
import yaml
from magnum import objects as magnum_objects
from magnum.api import attr_validator
from magnum.common import context, exception, neutron, octavia
from magnum.common import utils as magnum_utils
from oslo_config import cfg
from oslo_serialization import base64
from oslo_utils import strutils, uuidutils
from tenacity import retry, retry_if_exception_type

from magnum_cluster_api import clients
from magnum_cluster_api import exceptions as mcapi_exceptions
from magnum_cluster_api import image_utils, images, objects

AVAILABLE_OPERATING_SYSTEMS = ["ubuntu", "flatcar"]
CONF = cfg.CONF


def get_cluster_api_cloud_config_secret_name(cluster: magnum_objects.Cluster) -> str:
    return f"{cluster.stack_id}-cloud-config"


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


def get_cloud_ca_cert() -> str:
    """
    Get cloud ca certificate.
    """
    return magnum_utils.get_openstack_ca()


def get_capi_client_ca_cert() -> str:
    ca_file = CONF.capi_client.ca_file

    if ca_file:
        with open(ca_file) as fd:
            return fd.read()
    else:
        return ""


def generate_cloud_controller_manager_config(
    ctx: context.RequestContext,
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
) -> str:
    """
    Generate coniguration for openstack-cloud-controller-manager if it does
    already exist.
    """

    osc = clients.get_openstack_api(ctx)
    data = pykube.Secret.objects(api, namespace="magnum-system").get_by_name(
        get_cluster_api_cloud_config_secret_name(cluster)
    )
    clouds_yaml = base64.decode_as_text(data.obj["data"]["clouds.yaml"])
    cloud_config = yaml.safe_load(clouds_yaml)

    return textwrap.dedent(
        f"""\
        [Global]
        auth-url={osc.url_for(service_type="identity", interface="public")}
        region={cloud_config["clouds"]["default"]["region_name"]}
        application-credential-id={cloud_config["clouds"]["default"]["auth"]["application_credential_id"]}
        application-credential-secret={cloud_config["clouds"]["default"]["auth"]["application_credential_secret"]}
        tls-insecure={"false" if CONF.drivers.verify_ca else "true"}
        {"ca-file=/etc/config/ca.crt" if get_cloud_ca_cert() else ""}
        """
    )


def generate_manila_csi_cloud_config(
    ctx: context.RequestContext,
    api: pykube.HTTPClient,
    cluster: magnum_objects.Cluster,
) -> dict[str, str]:
    """
    Generate coniguration of Openstack authentication  for manila csi
    """
    osc = clients.get_openstack_api(ctx)
    data = pykube.Secret.objects(api, namespace="magnum-system").get_by_name(
        get_cluster_api_cloud_config_secret_name(cluster)
    )
    clouds_yaml = base64.decode_as_text(data.obj["data"]["clouds.yaml"])
    cloud_config = yaml.safe_load(clouds_yaml)

    config = {
        "os-authURL": osc.url_for(service_type="identity", interface="public"),
        "os-region": cloud_config["clouds"]["default"]["region_name"],
        "os-applicationCredentialID": cloud_config["clouds"]["default"]["auth"][
            "application_credential_id"
        ],
        "os-applicationCredentialSecret": cloud_config["clouds"]["default"]["auth"][
            "application_credential_secret"
        ],
        "os-TLSInsecure": (
            ("false" if CONF.drivers.verify_ca else "true")
            if cloud_config["clouds"]["default"]["verify"]
            else "true"
        ),
    }

    if get_cloud_ca_cert():
        config["os-certAuthorityPath"] = "/etc/config/ca.crt"

    return config


def get_kube_tag(cluster: magnum_objects.Cluster) -> str:
    return get_cluster_label(cluster, "kube_tag", "v1.25.3")


def get_auto_scaling_enabled(cluster: magnum_objects.Cluster) -> bool:
    return get_cluster_label_as_bool(cluster, "auto_scaling_enabled", False)


def get_cluster_container_infra_prefix(cluster: magnum_objects.Cluster) -> str:
    return get_cluster_label(
        cluster,
        "container_infra_prefix",
        "",
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


def generate_systemd_proxy_config(cluster: magnum_objects.Cluster):
    if (
        cluster.cluster_template.http_proxy is not None
        or cluster.cluster_template.https_proxy is not None
    ):
        return textwrap.dedent(
            """\
            [Service]
            Environment="http_proxy={http_proxy}"
            Environment="HTTP_PROXY={http_proxy}"
            Environment="https_proxy={https_proxy}"
            Environment="HTTPS_PROXY={https_proxy}"
            Environment="no_proxy={no_proxy}"
            Environment="NO_PROXY={no_proxy}"
            """
        ).format(
            http_proxy=cluster.cluster_template.http_proxy,
            https_proxy=cluster.cluster_template.https_proxy,
            no_proxy=cluster.cluster_template.no_proxy,
        )
    else:
        return ""


def generate_apt_proxy_config(cluster: magnum_objects.Cluster):
    if (
        cluster.cluster_template.http_proxy is not None
        or cluster.cluster_template.https_proxy is not None
    ):
        return textwrap.dedent(
            """\
            Acquire::http::Proxy "{http_proxy}";
            Acquire::https::Proxy "{https_proxy}";
            """
        ).format(
            http_proxy=cluster.cluster_template.http_proxy,
            https_proxy=cluster.cluster_template.https_proxy,
        )
    else:
        return ""


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


def format_event_message(event: pykube.Event):
    return "%s: %s" % (
        event.obj["reason"],
        event.obj["message"],
    )


def validate_flavor_name(cli: clients.OpenStackClients, flavor: str):
    """Check if a flavor with this specified name exists"""

    if flavor is None:
        return
    flavor_list = cli.nova().flavors.list()
    for f in flavor_list:
        if f.name == flavor:
            return
        if f.id == flavor:
            raise mcapi_exceptions.OpenstackFlavorInvalidName(flavor=flavor)
    raise exception.FlavorNotFound(flavor=flavor)


def validate_cluster(ctx: context.RequestContext, cluster: magnum_objects.Cluster):
    # Check master count
    if (cluster.master_count % 2) == 0:
        raise mcapi_exceptions.ClusterMasterCountEven
    # Validate flavors
    osc = clients.get_openstack_api(ctx)
    validate_flavor_name(osc, cluster.master_flavor_id)
    validate_flavor_name(osc, cluster.flavor_id)

    # Check if fixed_network exists
    if cluster.fixed_network:
        if uuidutils.is_uuid_like(cluster.fixed_network):
            neutron.get_network(
                ctx,
                cluster.fixed_network,
                source="id",
                target="name",
                external=False,
            )
        else:
            neutron.get_network(
                ctx,
                cluster.fixed_network,
                source="name",
                target="id",
                external=False,
            )

    # Check if fixed_subnet exists
    if cluster.fixed_subnet:
        if uuidutils.is_uuid_like(cluster.fixed_subnet):
            neutron.get_subnet(ctx, cluster.fixed_subnet, source="id", target="name")
        else:
            neutron.get_subnet(ctx, cluster.fixed_subnet, source="name", target="id")


def validate_nodegroup(
    nodegroup: magnum_objects.NodeGroup, ctx: context.RequestContext
):
    # Validate flavors
    osc = clients.get_openstack_api(ctx)
    validate_flavor_name(osc, nodegroup.flavor_id)


def get_operating_system(cluster: magnum_objects.Cluster):
    cluster_distro = cluster.cluster_template.cluster_distro
    for ops in AVAILABLE_OPERATING_SYSTEMS:
        if cluster_distro.startswith(ops):
            return ops
    return None


def get_image_uuid(image_ref: str, ctx: context.RequestContext):
    """Get image uuid from image ref

    :param image_ref: Image id or name
    """
    osc = clients.get_openstack_api(ctx)
    image_obj = attr_validator.validate_image(osc, image_ref)
    return image_obj.get("id")


def convert_to_rfc1123(input: str) -> str:
    """
    Convert a given string to RFC1123 format.

    :param input: The string to be converted.
    :type input: str

    :return: The converted string in RFC1123 format.
    :rtype: str
    """
    return re.sub(r"[^a-zA-Z0-9]+", "-", input).lower()


def get_keystone_auth_default_policy(cluster: magnum_objects.Cluster):
    default_policy = [
        {
            "resource": {
                "verbs": ["list"],
                "resources": ["pods", "services", "deployments", "pvc"],
                "version": "*",
                "namespace": "default",
            },
            "match": [
                {"type": "role", "values": ["member"]},
                {"type": "project", "values": [cluster.project_id]},
            ],
        }
    ]

    try:
        with open(CONF.kubernetes.keystone_auth_default_policy) as f:
            return json.loads(f.read())
    except Exception:
        return default_policy
