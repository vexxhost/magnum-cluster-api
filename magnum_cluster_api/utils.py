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

import base64 as stdlib_base64
import json
import re
import string
import textwrap
import typing

import pykube  # type: ignore
import shortuuid
import yaml
from magnum import objects as magnum_objects  # type: ignore
from magnum.api import attr_validator  # type: ignore
from magnum.common import context, exception, neutron, octavia  # type: ignore
from magnum.common import utils as magnum_utils
from novaclient import exceptions as nova_exception  # type: ignore
from novaclient.v2 import flavors  # type: ignore
from oslo_config import cfg  # type: ignore
from oslo_serialization import base64  # type: ignore
from oslo_utils import strutils, uuidutils  # type: ignore
from tenacity import retry, retry_if_exception_type

from magnum_cluster_api import clients
from magnum_cluster_api import exceptions as mcapi_exceptions
from magnum_cluster_api import image_utils, images, objects
from magnum_cluster_api.cache import ServerGroupCache

AVAILABLE_OPERATING_SYSTEMS = ["ubuntu", "flatcar", "rockylinux"]
DEFAULT_SERVER_GROUP_POLICIES = ["soft-anti-affinity"]
AVAILABLE_SERVER_GROUP_POLICIES = [
    "affinity",
    "anti-affinity",
    "soft-affinity",
    "soft-anti-affinity",
]
CONF = cfg.CONF


g_server_group_cache = ServerGroupCache()


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

    octavia_provider = cluster.labels.get("octavia_provider", "amphorav2")
    octavia_lb_algorithm = cluster.labels.get("octavia_lb_algorithm")
    octavia_lb_healthcheck = cluster.labels.get("octavia_lb_healthcheck", True)

    if octavia_provider in ("amphora", "amphorav2") and octavia_lb_algorithm is None:
        octavia_lb_algorithm = "ROUND_ROBIN"
    elif octavia_provider == "ovn" and octavia_lb_algorithm is None:
        octavia_lb_algorithm = "SOURCE_IP_PORT"
    elif octavia_provider == "ovn" and octavia_lb_algorithm != "SOURCE_IP_PORT":
        raise mcapi_exceptions.InvalidOctaviaLoadBalancerAlgorithm(
            octavia_lb_algorithm=octavia_lb_algorithm
        )

    return textwrap.dedent(
        f"""\
        [Global]
        auth-url={osc.url_for(service_type="identity", interface="public")}
        region={cloud_config["clouds"]["default"]["region_name"]}
        application-credential-id={cloud_config["clouds"]["default"]["auth"]["application_credential_id"]}
        application-credential-secret={cloud_config["clouds"]["default"]["auth"]["application_credential_secret"]}
        tls-insecure={"false" if CONF.drivers.verify_ca else "true"}
        {"ca-file=/etc/config/ca.crt" if magnum_utils.get_openstack_ca() else ""}
        [LoadBalancer]
        lb-provider={octavia_provider}
        lb-method={octavia_lb_algorithm}
        create-monitor={octavia_lb_healthcheck}
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

    if magnum_utils.get_openstack_ca():
        config["os-certAuthorityPath"] = "/etc/config/ca.crt"

    return config


def get_kube_tag(cluster: magnum_objects.Cluster) -> str:
    return cluster.labels.get("kube_tag", "v1.25.3")


def get_auto_scaling_enabled(cluster: magnum_objects.Cluster) -> bool:
    return get_cluster_label_as_bool(cluster, "auto_scaling_enabled", False)


def get_auto_healing_enabled(cluster: magnum_objects.Cluster) -> bool:
    return get_cluster_label_as_bool(cluster, "auto_healing_enabled", True)


def get_cluster_container_infra_prefix(cluster: magnum_objects.Cluster) -> str:
    return cluster.labels.get("container_infra_prefix", "")


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


def get_node_group_max_node_count(
    node_group: magnum_objects.NodeGroup,
) -> int:
    if node_group.max_node_count is None:
        return get_node_group_label_as_int(
            node_group,
            "max_node_count",
            node_group.min_node_count + 1,
        )
    return node_group.max_node_count


def get_node_group_label_as_bool(
    node_group: magnum_objects.NodeGroup,
    key: str,
    default: bool,
) -> bool:
    value = node_group.labels.get(key, default)
    return strutils.bool_from_string(value, strict=True)


def get_node_group_label_as_int(
    node_group: magnum_objects.NodeGroup,
    key: str,
    default: int,
) -> int:
    value = node_group.labels.get(key, str(default))
    return strutils.validate_integer(value, key)


def get_cluster_label_as_int(
    cluster: magnum_objects.Cluster, key: str, default: int
) -> int:
    value = cluster.labels.get(key, default)
    return strutils.validate_integer(value, key)


def get_cluster_label_as_bool(
    cluster: magnum_objects.Cluster, key: str, default: bool
) -> bool:
    value = cluster.labels.get(key, default)
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


def lookup_flavor(cli: clients.OpenStackClients, flavor: str) -> flavors.Flavor:
    """Lookup a flavor either by name or id."""

    if flavor is None:
        return
    flavor_list = cli.nova().flavors.list()
    for f in flavor_list:
        if f.name == flavor or f.id == flavor:
            return f
    raise exception.FlavorNotFound(flavor=flavor)


def lookup_image(cli: clients.OpenStackClients, image_ref: str) -> dict:
    """
    Get image object from image ref

    :param image_ref: Image id or name
    """
    return attr_validator.validate_image(cli, image_ref)


def validate_cluster(ctx: context.RequestContext, cluster: magnum_objects.Cluster):
    # Check network driver
    if cluster.cluster_template.network_driver not in ["cilium", "calico"]:
        raise mcapi_exceptions.UnsupportedCNI

    # Check master count
    if (cluster.master_count % 2) == 0:
        raise mcapi_exceptions.ClusterMasterCountEven

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


def validate_nodegroup_name(nodegroup: magnum_objects.NodeGroup):
    # Machine requires a lowercase RFC 1123 subdomain name.
    rgx = "[a-z0-9]([-a-z0-9]*[a-z0-9])?(.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*"
    if re.fullmatch(rgx, nodegroup.name) is None:
        raise mcapi_exceptions.MachineInvalidName(name=nodegroup.name)


def validate_nodegroup(nodegroup: magnum_objects.NodeGroup):
    validate_nodegroup_name(nodegroup)


def get_operating_system(cluster: magnum_objects.Cluster):
    cluster_distro = cluster.cluster_template.cluster_distro
    for ops in AVAILABLE_OPERATING_SYSTEMS:
        if cluster_distro.startswith(ops):
            return ops
    return None


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
            return json.loads(f.read().replace("$PROJECT_ID", cluster.project_id))
    except Exception:
        return default_policy


def kube_apply_patch(resource):
    if "metadata" in resource.obj:
        resource.obj["metadata"]["managedFields"] = None

    resp = resource.api.patch(
        **resource.api_kwargs(
            headers={
                "Content-Type": "application/apply-patch+yaml",
            },
            params={
                "fieldManager": "atmosphere-operator",
                "force": True,
            },
            data=json.dumps(resource.obj),
        )
    )

    resource.api.raise_for_status(resp)
    resource.set_obj(resp.json())


def generate_api_cert_san_list(cluster: magnum_objects.Cluster):
    cert_sans = cluster.labels.get("api_server_cert_sans", "")
    additional_cert_sans_list = cert_sans.split(",")

    # Add the additional cert SANs to the template
    return "\n".join(f"- {san}" for san in additional_cert_sans_list if san)


def get_server_group_id(
    ctx: context.RequestContext,
    name: str,
    project_id: typing.Optional[str] = None,
):
    if g_server_group_cache.get(project_id, name):
        return g_server_group_cache.get(project_id, name)

    # Check if the server group exists already
    osc = clients.get_openstack_api(ctx)
    server_groups = osc.nova().server_groups.list(all_projects=ctx.is_admin)
    server_group_id_list = []
    for sg in server_groups:
        if sg.name == name:
            server_group_id_list.append(sg.id)

    if len(server_group_id_list) == 1:
        g_server_group_cache.set(project_id, name, server_group_id_list[0])
        return server_group_id_list[0]

    if len(server_group_id_list) > 1:
        raise exception.Conflict(f"too many server groups with name {name} were found")

    return None


def _get_node_group_server_group_policies(
    node_group: magnum_objects.NodeGroup,
    cluster: magnum_objects.Cluster,
):
    policies = node_group.labels.get("server_group_policies", "")
    policies = [s for s in policies.split(",") if s in AVAILABLE_SERVER_GROUP_POLICIES]
    if policies:
        return policies
    else:
        return _get_controlplane_server_group_policies(cluster)


def _get_controlplane_server_group_policies(
    cluster: magnum_objects.Cluster,
):
    policies = cluster.labels.get("server_group_policies", "")
    policies = [s for s in policies.split(",") if s in AVAILABLE_SERVER_GROUP_POLICIES]
    if policies:
        return policies
    else:
        return DEFAULT_SERVER_GROUP_POLICIES


def is_node_group_different_failure_domain(
    node_group: magnum_objects.NodeGroup,
    cluster: magnum_objects.Cluster,
) -> bool:
    res = get_node_group_label_as_bool(node_group, "different_failure_domain", False)
    if not res:
        res = is_controlplane_different_failure_domain(cluster)
    return res


def is_controlplane_different_failure_domain(
    cluster: magnum_objects.Cluster,
) -> bool:
    return get_cluster_label_as_bool(cluster, "different_failure_domain", False)


def ensure_controlplane_server_group(
    ctx: context.RequestContext,
    cluster: magnum_objects.Cluster,
):
    return _ensure_server_group(
        name=cluster.stack_id,
        ctx=ctx,
        policies=_get_controlplane_server_group_policies(cluster),
        project_id=cluster.project_id,
    )


def ensure_worker_server_group(
    ctx: context.RequestContext,
    cluster: magnum_objects.Cluster,
    node_group: magnum_objects.NodeGroup,
):
    return _ensure_server_group(
        name=f"{cluster.stack_id}-{node_group.name}",
        ctx=ctx,
        policies=_get_node_group_server_group_policies(node_group, cluster),
        project_id=cluster.project_id,
    )


def delete_controlplane_server_group(
    ctx: context.RequestContext,
    cluster: magnum_objects.Cluster,
):
    _delete_server_group(
        name=cluster.stack_id,
        ctx=ctx,
        project_id=cluster.project_id,
    )


def delete_worker_server_group(
    ctx: context.RequestContext,
    cluster: magnum_objects.Cluster,
    node_group: magnum_objects.NodeGroup,
):
    _delete_server_group(
        name=f"{cluster.stack_id}-{node_group.name}",
        ctx=ctx,
        project_id=cluster.project_id,
    )


def _ensure_server_group(
    name: str,
    ctx: context.RequestContext,
    policies: typing.List[str] = None,
    project_id: typing.Optional[str] = None,
):
    # Retrieve existing server group id
    server_group_id = get_server_group_id(ctx, name, project_id)
    if server_group_id:
        return server_group_id

    # Create a new server group
    osc = clients.get_openstack_api(ctx)
    if not policies:
        policies = DEFAULT_SERVER_GROUP_POLICIES

    # NOTE(oleks): Requires API microversion 2.15 or later for soft-affinity and soft-anti-affinity policy rules.
    server_group = osc.nova().server_groups.create(name=name, policies=policies)
    g_server_group_cache.set(project_id, name, server_group.id)
    return server_group.id


def _delete_server_group(
    name: str,
    ctx: context.RequestContext,
    project_id: typing.Optional[str] = None,
):
    server_group_id = get_server_group_id(ctx, name, project_id)
    if server_group_id is None:
        return

    osc = clients.get_openstack_api(ctx)
    try:
        osc.nova().server_groups.delete(server_group_id)
    except nova_exception.NotFound:
        return


def get_fixed_network_id(context, network):
    if network and not uuidutils.is_uuid_like(network):
        return neutron.get_network(
            context, network, source="name", target="id", external=False
        )
    else:
        return network


# ---------------------------------------------------------------------------
# extra_cloud_init feature: extra_files, extra_pre/post_kubeadm_commands
# ---------------------------------------------------------------------------

# Hard caps mirror the Rust-side `MAX_EXTRA_FILES`,
# `MAX_PRE_KUBEADM_COMMANDS`, and `MAX_POST_KUBEADM_COMMANDS` constants in
# `src/features/extra_cloud_init.rs`.  The ClusterClass renders a fixed
# number of patch slots; entries beyond the cap would be silently dropped
# by CAPI, so we reject them here with a clear error.
EXTRA_CLOUD_INIT_MAX_FILES = 10
EXTRA_CLOUD_INIT_MAX_PRE_COMMANDS = 16
EXTRA_CLOUD_INIT_MAX_POST_COMMANDS = 16

_DEFAULT_FILE_OWNER = "root:root"
_DEFAULT_FILE_PERMISSIONS = "0644"

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _looks_like_base64_text(value: str) -> bool:
    """Heuristic: detect content that is almost certainly already base64.

    Used to surface a clear error when an operator pre-encodes ``content`` but
    forgets to set ``encoding: base64`` (which would otherwise silently double
    encode the payload).  The heuristic is deliberately conservative — it only
    matches strings that look exactly like canonical base64 (no whitespace, no
    punctuation), are long enough to be intentional, and round-trip through
    ``b64decode`` to valid UTF-8.  Any plausible script or config file with
    spaces, newlines, or special characters will fail the check.
    """
    if not value or len(value) < 16 or len(value) % 4 != 0:
        return False
    if not _BASE64_RE.match(value):
        return False
    try:
        decoded = stdlib_base64.b64decode(value, validate=True)
        decoded.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    return True


def _decode_extra_files_label(value: str) -> typing.List[dict]:
    """Decode the YAML/JSON payload of an `extra_files` label.

    The label value may be supplied either as a base64-wrapped YAML/JSON list
    (recommended for transport-safety through Magnum's comma-separated label
    parser) or as a plain YAML/JSON list when the operator pipeline already
    handles encoding (e.g. Heat parameters, Terraform, kubectl YAML manifests).
    An empty or missing value yields an empty list.
    """
    if not value:
        return []

    # Try base64-wrapped form first (the recommended/documented path).
    decoded: typing.Optional[str] = None
    try:
        decoded = stdlib_base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        decoded = None

    candidates = [decoded, value] if decoded is not None else [value]
    last_error: typing.Optional[Exception] = None
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            parsed = yaml.safe_load(candidate)
        except yaml.YAMLError as exc:
            last_error = exc
            continue
        if parsed is None:
            return []
        if isinstance(parsed, list):
            return parsed
        last_error = ValueError("extra_files label must decode to a YAML/JSON list")

    raise exception.InvalidParameterValue(
        err=(
            "extra_files label must be a base64-wrapped YAML/JSON list or a "
            f"plain YAML/JSON list: {last_error}"
        )
    )


def _normalize_extra_file(entry: dict) -> dict:
    """Validate one entry and re-emit it in the wire shape."""
    if not isinstance(entry, dict):
        raise exception.InvalidParameterValue(
            err="extra_files entries must be mappings"
        )
    path = entry.get("path")
    if not path or not isinstance(path, str):
        raise exception.InvalidParameterValue(
            err="extra_files entries must include a non-empty 'path' string"
        )
    if not path.startswith("/"):
        raise exception.InvalidParameterValue(
            err=f"extra_files path must be absolute: {path!r}"
        )

    raw_content = entry.get("content", "")
    if not isinstance(raw_content, str):
        raise exception.InvalidParameterValue(
            err=f"extra_files content for {path!r} must be a string"
        )
    encoding = entry.get("encoding")
    if encoding is None:
        if _looks_like_base64_text(raw_content):
            raise exception.InvalidParameterValue(
                err=(
                    f"extra_files content for {path!r} appears to already be "
                    "base64-encoded but no 'encoding' field was set; either "
                    "remove the pre-encoding or add `encoding: base64` to the "
                    "entry to avoid double-encoding"
                )
            )
        wire_content = stdlib_base64.b64encode(raw_content.encode("utf-8")).decode(
            "ascii"
        )
    elif encoding == "base64":
        # Operator pre-encoded the content; round-trip it through the
        # validator so we reject obvious corruption early.
        try:
            stdlib_base64.b64decode(raw_content, validate=True)
        except ValueError as exc:
            raise exception.InvalidParameterValue(
                err=(
                    f"extra_files content for {path!r} is declared base64 but "
                    f"is not valid base64: {exc}"
                )
            )
        wire_content = raw_content
    else:
        raise exception.InvalidParameterValue(
            err=(
                f"extra_files entry {path!r} has unsupported encoding "
                f"{encoding!r} (expected omit or 'base64')"
            )
        )

    owner = entry.get("owner", _DEFAULT_FILE_OWNER)
    if not isinstance(owner, str) or not owner:
        raise exception.InvalidParameterValue(
            err=f"extra_files owner for {path!r} must be a non-empty string"
        )
    permissions = entry.get("permissions", _DEFAULT_FILE_PERMISSIONS)
    if isinstance(permissions, int):
        permissions = format(permissions, "04o")
    if not isinstance(permissions, str) or not permissions:
        raise exception.InvalidParameterValue(
            err=(
                f"extra_files permissions for {path!r} must be a non-empty "
                f"string (e.g. '0600')"
            )
        )

    return {
        "path": path,
        "owner": owner,
        "permissions": permissions,
        "content": wire_content,
    }


def get_extra_files(
    cluster: magnum_objects.Cluster,
    node_group: typing.Optional[magnum_objects.NodeGroup] = None,
) -> typing.List[dict]:
    """Build the `extraFiles` topology variable for one cluster + node group.

    Per-node-group override semantics: when ``node_group`` is provided **and**
    its labels include a non-empty ``extra_files`` entry, the node group's
    list fully replaces the cluster-level list for machines in that node
    group.  When the node group does not declare its own ``extra_files``, the
    machines inherit the cluster-level list.  The two are never merged — this
    matches CAPI's ClusterClass variable-override contract (overrides replace
    parent values) and lets operators ship distinct files to control plane,
    worker-A, worker-B node groups, etc.

    Capped at :data:`EXTRA_CLOUD_INIT_MAX_FILES`; raises
    :class:`magnum.common.exception.InvalidParameterValue` if exceeded.
    """
    if node_group is not None and node_group.labels.get("extra_files"):
        raw = node_group.labels.get("extra_files", "")
    else:
        raw = cluster.labels.get("extra_files", "")
    entries = [_normalize_extra_file(e) for e in _decode_extra_files_label(raw)]
    if len(entries) > EXTRA_CLOUD_INIT_MAX_FILES:
        raise exception.InvalidParameterValue(
            err=(
                f"extra_files exceeds the maximum of "
                f"{EXTRA_CLOUD_INIT_MAX_FILES} entries (got {len(entries)})"
            )
        )
    return entries


def _split_kubeadm_commands(value: str) -> typing.List[str]:
    """Split a ``;;``-delimited command string, dropping empty segments.

    The delimiter is the *double* semicolon ``;;`` (not a single ``;``):
    each segment becomes its own ``runcmd`` entry in the rendered cloud-init
    user-data, and cloud-init executes each entry in its own
    ``/bin/sh -c <entry>`` subshell.  A single ``;`` is therefore part of
    one shell command and is forwarded verbatim to that subshell, e.g.

    * ``"a; b"``  → one runcmd entry: ``a; b``
      (single ``sh -c`` invocation, ``b`` runs after ``a`` regardless of
      ``a``'s exit code)
    * ``"a;;b"`` → two runcmd entries: ``a`` and ``b``
      (separate ``sh -c`` invocations; cloud-init records per-entry status)

    Use ``;;`` whenever you want each command to be observable as its own
    runcmd entry (e.g. for failure attribution) and to avoid the
    cloud-init quirk that shell options (``set -e``, ``trap``, exported
    variables) installed in one entry do not propagate to the next.
    """
    if not value:
        return []
    return [segment.strip() for segment in value.split(";;") if segment.strip()]


def _get_extra_kubeadm_commands(
    cluster: magnum_objects.Cluster,
    node_group: typing.Optional[magnum_objects.NodeGroup],
    label: str,
    cap: int,
) -> typing.List[str]:
    if node_group is not None and node_group.labels.get(label):
        raw = node_group.labels.get(label, "")
    else:
        raw = cluster.labels.get(label, "")
    cmds = _split_kubeadm_commands(raw)
    if len(cmds) > cap:
        raise exception.InvalidParameterValue(
            err=(f"{label} exceeds the maximum of {cap} entries " f"(got {len(cmds)})")
        )
    return cmds


def get_extra_pre_kubeadm_commands(
    cluster: magnum_objects.Cluster,
    node_group: typing.Optional[magnum_objects.NodeGroup] = None,
) -> typing.List[str]:
    """``;;``-separated ``extra_pre_kubeadm_commands`` label.

    Each ``;;``-separated segment becomes its own cloud-init ``runcmd``
    entry; a single ``;`` is forwarded verbatim as part of one shell
    command.  See :func:`_split_kubeadm_commands` for the full delimiter
    semantics and rationale.

    Per-node-group override semantics: when ``node_group`` declares its own
    ``extra_pre_kubeadm_commands`` label, the node group's list fully
    replaces the cluster-level list for machines in that node group;
    otherwise the cluster-level list is used.  See :func:`get_extra_files`
    for the rationale.
    """
    return _get_extra_kubeadm_commands(
        cluster,
        node_group,
        "extra_pre_kubeadm_commands",
        EXTRA_CLOUD_INIT_MAX_PRE_COMMANDS,
    )


def get_extra_post_kubeadm_commands(
    cluster: magnum_objects.Cluster,
    node_group: typing.Optional[magnum_objects.NodeGroup] = None,
) -> typing.List[str]:
    """``;;``-separated ``extra_post_kubeadm_commands`` label.

    Each ``;;``-separated segment becomes its own cloud-init ``runcmd``
    entry; a single ``;`` is forwarded verbatim as part of one shell
    command.  See :func:`_split_kubeadm_commands` for the full delimiter
    semantics and rationale.

    Per-node-group override semantics — see :func:`get_extra_files`.
    """
    return _get_extra_kubeadm_commands(
        cluster,
        node_group,
        "extra_post_kubeadm_commands",
        EXTRA_CLOUD_INIT_MAX_POST_COMMANDS,
    )
