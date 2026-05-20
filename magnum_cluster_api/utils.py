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
import time
import typing

import pykube  # type: ignore
import shortuuid
import yaml
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import context, exception  # type: ignore
from magnum.common import utils as magnum_utils
from openstack import exceptions as sdk_exceptions  # type: ignore
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


def _sdk_resource_value(resource, key, default=None):
    value = getattr(resource, key, None)
    if value is not None:
        return value

    if isinstance(resource, dict):
        return resource.get(key, default)

    try:
        return resource[key]
    except (KeyError, TypeError):
        pass

    properties = getattr(resource, "properties", None)
    if hasattr(properties, "get"):
        return properties.get(key, default)

    return default


def _network_is_external(network) -> bool:
    value = _sdk_resource_value(network, "is_router_external", None)
    if value is None:
        value = _sdk_resource_value(network, "router:external", False)
    return bool(value)


def _network_matches_external(network, external: bool) -> bool:
    return _network_is_external(network) is external


def _raise_network_not_found(network, external):
    if external:
        raise exception.ExternalNetworkNotFound(network=network)
    raise exception.FixedNetworkNotFound(network=network)


def _get_network_value(ctx, network, source, target, external):
    osc = clients.get_openstack_api(ctx)

    if source == "id":
        try:
            sdk_network = osc.network.get_network(network)
        except (sdk_exceptions.NotFoundException, sdk_exceptions.ResourceNotFound):
            _raise_network_not_found(network, external)

        if not _network_matches_external(sdk_network, external):
            _raise_network_not_found(network, external)

        return _sdk_resource_value(sdk_network, target)

    networks = [
        sdk_network
        for sdk_network in osc.network.networks(name=network)
        if _sdk_resource_value(sdk_network, source) == network
        and _network_matches_external(sdk_network, external)
    ]

    if len(networks) == 0:
        _raise_network_not_found(network, external)

    if len(networks) > 1:
        raise exception.Conflict(
            "Multiple networks exist with same name '%s'. Please use the "
            "network ID instead." % network
        )

    return _sdk_resource_value(networks[0], target)


def _get_subnet_value(ctx, subnet, source, target):
    osc = clients.get_openstack_api(ctx)

    if source == "id":
        try:
            sdk_subnet = osc.network.get_subnet(subnet)
        except (sdk_exceptions.NotFoundException, sdk_exceptions.ResourceNotFound):
            raise exception.FixedSubnetNotFound(subnet=subnet)

        return _sdk_resource_value(sdk_subnet, target)

    subnets = [
        sdk_subnet
        for sdk_subnet in osc.network.subnets(name=subnet)
        if _sdk_resource_value(sdk_subnet, source) == subnet
    ]

    if len(subnets) == 0:
        raise exception.FixedSubnetNotFound(subnet=subnet)

    if len(subnets) > 1:
        raise exception.Conflict(
            "Multiple subnets exist with same name '%s'. Please use the "
            "subnet ID instead." % subnet
        )

    return _sdk_resource_value(subnets[0], target)


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
        auth-url={osc.endpoint_for(service_type="identity", interface="public")}
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
        "os-authURL": osc.endpoint_for(service_type="identity", interface="public"),
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
        octavia_admin_client = admin_clients.load_balancer
        octavia_client = user_clients.load_balancer

        # Get load balancers created for service/ingress
        lbs = [
            lb
            for lb in octavia_client.load_balancers()
            if re.match(pattern, lb.description)
        ]
        deleted = _delete_loadbalancers(
            ctx,
            lbs,
            cluster,
            octavia_admin_client,
            remove_fip=True,
        )
        candidates.update(deleted)

        if not candidates:
            return

        _wait_for_loadbalancers_deleted(octavia_client, candidates)
    except Exception as e:
        raise exception.PreDeletionFailed(cluster_uuid=cluster.uuid, msg=str(e))


def _delete_loadbalancers(
    ctx,
    lbs,
    cluster,
    octavia_client,
    remove_fip=False,
    cascade=True,
):
    candidates = set()

    for lb in lbs:
        if lb.provisioning_status not in ["PENDING_DELETE", "DELETED"]:
            octavia_client.delete_load_balancer(lb.id, cascade=cascade)
            candidates.add(lb.id)

            if remove_fip:
                neutron.delete_floatingip(ctx, lb.vip_port_id, cluster)

    return candidates


def _wait_for_loadbalancers_deleted(octavia_client, deleted_lbs):
    timeout = CONF.cluster.pre_delete_lb_timeout
    start_time = time.time()

    while True:
        lb_ids = {
            lb.id
            for lb in octavia_client.load_balancers()
            if lb.provisioning_status != "DELETED"
        }
        if not (deleted_lbs & lb_ids):
            break

        if (time.time() - timeout) > start_time:
            raise Exception(
                "Timeout waiting for the load balancers "
                "%s to be deleted." % deleted_lbs
            )

        time.sleep(1)


def format_event_message(event: pykube.Event):
    return "%s: %s" % (
        event.obj["reason"],
        event.obj["message"],
    )


def lookup_flavor(cli, flavor: str):
    """Lookup a flavor either by name or id."""

    if flavor is None:
        return
    flavor_list = list(cli.compute.flavors())
    for f in flavor_list:
        if f.name == flavor or f.id == flavor:
            return f
    raise exception.FlavorNotFound(flavor=flavor)


def lookup_image(cli, image_ref: str) -> dict:
    """
    Get image object from image ref

    :param image_ref: Image id or name
    """
    try:
        image = cli.image.find_image(image_ref, ignore_missing=False)
    except (sdk_exceptions.NotFoundException, exception.ResourceNotFound):
        raise exception.ImageNotFound(image_id=image_ref)
    except sdk_exceptions.DuplicateResource:
        raise exception.Conflict(
            "Multiple images exist with same name '%s'. "
            "Please use the image ID instead." % image_ref
        )
    except sdk_exceptions.ForbiddenException:
        raise exception.ImageNotAuthorized(image_id=image_ref)

    if not image.os_distro:
        raise exception.OSDistroFieldNotFound(image_id=image_ref)

    return image


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
            _get_network_value(
                ctx,
                cluster.fixed_network,
                source="id",
                target="name",
                external=False,
            )
        else:
            _get_network_value(
                ctx,
                cluster.fixed_network,
                source="name",
                target="id",
                external=False,
            )

    # Check if fixed_subnet exists
    if cluster.fixed_subnet:
        if uuidutils.is_uuid_like(cluster.fixed_subnet):
            _get_subnet_value(ctx, cluster.fixed_subnet, source="id", target="name")
        else:
            _get_subnet_value(ctx, cluster.fixed_subnet, source="name", target="id")


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
    server_groups = osc.compute.server_groups(all_projects=ctx.is_admin)
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
    server_group = osc.compute.create_server_group(name=name, policies=policies)
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
        osc.compute.delete_server_group(server_group_id, ignore_missing=True)
    except (sdk_exceptions.NotFoundException, sdk_exceptions.ResourceNotFound):
        return


def get_fixed_network_id(context, network):
    if network and not uuidutils.is_uuid_like(network):
        return _get_network_value(
            context, network, source="name", target="id", external=False
        )
    else:
        return network


def get_external_network_id(context, network):
    if network and uuidutils.is_uuid_like(network):
        return network

    return _get_network_value(
        context, network, source="name", target="id", external=True
    )


def get_fixed_subnet_id(context, subnet):
    if subnet and not uuidutils.is_uuid_like(subnet):
        return _get_subnet_value(context, subnet, source="name", target="id")

    return subnet
