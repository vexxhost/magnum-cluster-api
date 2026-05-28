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
CONFIG_PROFILE_RESERVED_FIELDS = {
    "apiVersion",
    "kind",
    "nodegroups",
}
CONFIG_PROFILE_SELECTOR_LABELS = (
    "config_profile",
    "nodegroup_config_profile_set",
)
CONFIG_PROFILES_CONFIGMAP = "mcapi-config-profiles"
CONFIG_PROFILE_FIELDS = {
    "kubeletConfig",
    "files",
    "preKubeadmCommands",
    "postKubeadmCommands",
}
CONFIG_PROFILE_STRING_KUBELET_FIELDS = {
    "reservedSystemCPUs",
}
CONFIG_PROFILE_MAX_FILES = 10
CONFIG_PROFILE_MAX_PRE_COMMANDS = 16
CONFIG_PROFILE_MAX_POST_COMMANDS = 16
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


def reject_config_profile_label_overrides(
    cluster: magnum_objects.Cluster,
) -> None:
    """Reject create-time profile selector overrides outside templates."""
    template = getattr(cluster, "cluster_template", None)
    template_labels = getattr(template, "labels", None) or {}
    cluster_labels = cluster.labels or {}
    for label in CONFIG_PROFILE_SELECTOR_LABELS:
        if label not in cluster_labels:
            continue
        if cluster_labels[label] == template_labels.get(label):
            continue
        raise exception.Invalid(
            "Invalid value for %(label)s: %(value)s. This label must be set "
            "on the cluster template and cannot be overridden during cluster "
            "creation."
            % {
                "label": label,
                "value": cluster_labels[label],
            }
        )


def sync_config_profile_labels_from_template(
    cluster: magnum_objects.Cluster,
    cluster_template: magnum_objects.ClusterTemplate,
) -> None:
    """Copy config profile selector labels from a target template."""
    if cluster.labels is None:
        cluster.labels = {}
    template_labels = getattr(cluster_template, "labels", None) or {}
    for label in CONFIG_PROFILE_SELECTOR_LABELS:
        if label in template_labels:
            cluster.labels[label] = template_labels[label]
        else:
            cluster.labels.pop(label, None)


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


def validate_cluster_label_in_list(
    cluster: magnum_objects.Cluster,
    key: str,
    allowed_values: list[str],
) -> None:
    value = cluster.labels.get(key)
    if not value:
        return
    if value not in allowed_values:
        raise exception.Invalid(
            "Invalid value for %(key)s: %(value)s. Allowed values: %(allowed)s."
            % {
                "key": key,
                "value": value,
                "allowed": ", ".join(allowed_values),
            }
        )


def validate_config_profile_labels(
    cluster: magnum_objects.Cluster,
    api: pykube.HTTPClient | None = None,
    namespace: str = "magnum-system",
) -> None:
    get_config_profile_defaults(
        cluster.labels.get("config_profile", ""),
        api,
        namespace,
    )
    get_nodegroup_config_profile_set(
        cluster.labels.get("nodegroup_config_profile_set", ""),
        api,
        namespace,
    )


def validate_config_profile(
    profile: str,
    fields: typing.Any,
) -> typing.Dict[str, typing.Any]:
    if not isinstance(fields, dict):
        raise exception.Invalid(
            "Invalid config profile %(profile)s. Expected a YAML object."
            % {"profile": profile}
        )

    unsupported = set(fields) - CONFIG_PROFILE_FIELDS
    if unsupported:
        raise exception.Invalid(
            "Unsupported config profile field %(field)s in %(profile)s."
            % {"field": sorted(unsupported)[0], "profile": profile}
        )
    kubelet_fields = fields.get("kubeletConfig", {})
    if kubelet_fields is None:
        kubelet_fields = {}
    if not isinstance(kubelet_fields, dict):
        raise exception.Invalid(
            "Invalid kubeletConfig in config profile %(profile)s. "
            "Expected a YAML object." % {"profile": profile}
        )
    reserved_fields = set(kubelet_fields) & CONFIG_PROFILE_RESERVED_FIELDS
    if reserved_fields:
        raise exception.Invalid(
            "Unsupported config profile field %(field)s in %(profile)s. "
            "Magnum renders this field itself."
            % {"field": sorted(reserved_fields)[0], "profile": profile}
        )
    for field in sorted(CONFIG_PROFILE_STRING_KUBELET_FIELDS):
        if field in kubelet_fields and not isinstance(kubelet_fields[field], str):
            raise exception.Invalid(
                "Invalid kubeletConfig.%(field)s in config profile %(profile)s. "
                "Expected a YAML string."
                % {"field": field, "profile": profile}
            )

    return fields


def get_config_profile_data(
    api: pykube.HTTPClient,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Any]:
    config_map = pykube.ConfigMap.objects(api, namespace=namespace).get_or_none(
        name=CONFIG_PROFILES_CONFIGMAP
    )
    if config_map is None:
        return {}

    profiles: typing.Dict[str, typing.Any] = {}
    for name, raw_profile in config_map.obj.get("data", {}).items():
        try:
            fields = yaml.safe_load(raw_profile) or {}
        except yaml.YAMLError as exc:
            raise exception.Invalid(
                "Invalid YAML in config profile %(profile)s: %(error)s."
                % {"profile": name, "error": exc}
            )
        profiles[name] = fields
    return profiles


def get_config_profiles(
    api: pykube.HTTPClient,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    profiles: typing.Dict[str, typing.Dict[str, typing.Any]] = {}
    for name, fields in get_config_profile_data(api, namespace).items():
        if isinstance(fields, dict) and set(fields) == {"nodegroups"}:
            continue
        profiles[name] = validate_config_profile(name, fields)
    return profiles


def get_config_profile_defaults(
    profile: str,
    api: pykube.HTTPClient | None,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Any]:
    if not profile:
        return {}
    if api is None:
        raise exception.Invalid(
            "config_profile requires access to the management Kubernetes " "cluster."
        )
    profiles = get_config_profiles(api, namespace)
    if profile not in profiles:
        if not profiles:
            raise exception.Invalid(
                "Invalid value for config_profile: %(value)s. No profiles "
                "are registered in ConfigMap %(configmap)s in namespace %(namespace)s."
                % {
                    "value": profile,
                    "configmap": CONFIG_PROFILES_CONFIGMAP,
                    "namespace": namespace,
                }
            )
        raise exception.Invalid(
            "Invalid value for config_profile: %(value)s. "
            "Allowed values: %(allowed)s."
            % {
                "value": profile,
                "allowed": ", ".join(sorted(profiles)),
            }
        )
    return profiles[profile]


def _get_config_profile_kubelet_fields(
    fields: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    kubelet_fields = fields.get("kubeletConfig") or {}
    if not isinstance(kubelet_fields, dict):
        raise exception.Invalid("config profile kubeletConfig must be a YAML object.")
    return kubelet_fields


def _get_config_profile_list(
    fields: typing.Dict[str, typing.Any],
    key: str,
    max_items: int,
) -> list[typing.Any]:
    value = fields.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise exception.Invalid(
            "config profile %(key)s must be a YAML list." % {"key": key}
        )
    if len(value) > max_items:
        raise exception.Invalid(
            "config profile %(key)s supports at most %(max)d entries."
            % {"key": key, "max": max_items}
        )
    return value


def _normalise_config_profile_file(
    entry: typing.Any,
) -> typing.Dict[str, typing.Any]:
    if not isinstance(entry, dict):
        raise exception.Invalid("config profile files entries must be YAML objects.")

    unsupported = set(entry) - {
        "append",
        "content",
        "contentFrom",
        "encoding",
        "owner",
        "path",
        "permissions",
    }
    if unsupported:
        raise exception.Invalid(
            "Unsupported config profile file field %(field)s."
            % {"field": sorted(unsupported)[0]}
        )

    path = entry.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        raise exception.Invalid(
            "config profile files entries must set an absolute path."
        )

    has_content = "content" in entry
    has_content_from = "contentFrom" in entry
    if has_content == has_content_from:
        raise exception.Invalid(
            "config profile file %(path)s must set exactly one of content or contentFrom."
            % {"path": path}
        )

    file_entry: typing.Dict[str, typing.Any] = {"path": path}

    for key in ("append", "contentFrom", "owner"):
        if key in entry:
            file_entry[key] = entry[key]

    permissions = entry.get("permissions", "0644")
    if isinstance(permissions, int):
        permissions = f"{permissions:04o}"
    if not isinstance(permissions, str):
        raise exception.Invalid(
            "config profile file %(path)s permissions must be a string."
            % {"path": path}
        )
    file_entry["permissions"] = permissions

    if has_content:
        content = entry["content"]
        if not isinstance(content, str):
            raise exception.Invalid(
                "config profile file %(path)s content must be a string."
                % {"path": path}
            )
        encoding = entry.get("encoding")
        if encoding is None:
            file_entry["content"] = stdlib_base64.b64encode(
                content.encode("utf-8")
            ).decode("ascii")
            file_entry["encoding"] = "base64"
        else:
            if encoding not in {"base64", "gzip", "gzip+base64"}:
                raise exception.Invalid(
                    "Unsupported config profile file %(path)s encoding %(encoding)s."
                    % {"path": path, "encoding": encoding}
                )
            file_entry["content"] = content
            file_entry["encoding"] = encoding

    return file_entry


def _render_config_profile_yaml(value: typing.Dict[str, typing.Any]) -> str:
    return yaml.safe_dump(
        value,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()


def _get_config_profile_commands(
    fields: typing.Dict[str, typing.Any],
    key: str,
    max_items: int,
) -> list[str]:
    commands = _get_config_profile_list(fields, key, max_items)
    for command in commands:
        if not isinstance(command, str) or not command:
            raise exception.Invalid(
                "config profile %(key)s entries must be non-empty strings."
                % {"key": key}
            )
    return commands


def validate_nodegroup_config_profile_set(
    profile_set: str,
    fields: typing.Any,
    profiles: typing.Dict[str, typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Dict[str, str]]:
    if not isinstance(fields, dict):
        raise exception.Invalid(
            "Invalid nodegroup config profile set %(profile)s. "
            "Expected a YAML object." % {"profile": profile_set}
        )

    unsupported = set(fields) - {"nodegroups"}
    if unsupported:
        raise exception.Invalid(
            "Unsupported nodegroup config profile set field %(field)s "
            "in %(profile)s. Supported fields: nodegroups."
            % {"field": sorted(unsupported)[0], "profile": profile_set}
        )

    nodegroups = fields.get("nodegroups", {})
    if not isinstance(nodegroups, dict):
        raise exception.Invalid(
            "Invalid nodegroups in nodegroup config profile set "
            "%(profile)s. Expected a YAML object." % {"profile": profile_set}
        )

    config: typing.Dict[str, typing.Dict[str, str]] = {}
    for nodegroup_name, nodegroup_config in nodegroups.items():
        if not isinstance(nodegroup_config, dict):
            raise exception.Invalid(
                "Invalid nodegroup %(nodegroup)s in nodegroup config "
                "profile set %(profile)s. Expected a YAML object."
                % {"nodegroup": nodegroup_name, "profile": profile_set}
            )

        unsupported = set(nodegroup_config) - {"profile"}
        if unsupported:
            raise exception.Invalid(
                "Unsupported field %(field)s for nodegroup %(nodegroup)s in "
                "nodegroup config profile set %(profile)s. Supported "
                "field: profile."
                % {
                    "field": sorted(unsupported)[0],
                    "nodegroup": nodegroup_name,
                    "profile": profile_set,
                }
            )

        config_profile = nodegroup_config.get("profile")
        if not config_profile:
            raise exception.Invalid(
                "Nodegroup %(nodegroup)s in nodegroup config profile "
                "set %(profile)s must set profile."
                % {"nodegroup": nodegroup_name, "profile": profile_set}
            )
        if config_profile not in profiles:
            raise exception.Invalid(
                "Invalid profile %(value)s for nodegroup "
                "%(nodegroup)s in nodegroup config profile set "
                "%(profile)s. Allowed values: %(allowed)s."
                % {
                    "value": config_profile,
                    "nodegroup": nodegroup_name,
                    "profile": profile_set,
                    "allowed": ", ".join(sorted(profiles)),
                }
            )

        config[nodegroup_name] = {"profile": config_profile}

    return config


def get_nodegroup_config_profile_set(
    profile_set: str,
    api: pykube.HTTPClient | None,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Dict[str, str]]:
    if not profile_set:
        return {}
    if api is None:
        raise exception.Invalid(
            "nodegroup_config_profile_set requires access to the "
            "management Kubernetes cluster."
        )

    profile_data = get_config_profile_data(api, namespace)
    if profile_set not in profile_data:
        if not profile_data:
            raise exception.Invalid(
                "Invalid value for nodegroup_config_profile_set: "
                "%(value)s. No profiles are registered in ConfigMap "
                "%(configmap)s in namespace %(namespace)s."
                % {
                    "value": profile_set,
                    "configmap": CONFIG_PROFILES_CONFIGMAP,
                    "namespace": namespace,
                }
            )
        raise exception.Invalid(
            "Invalid value for nodegroup_config_profile_set: %(value)s. "
            "Allowed values: %(allowed)s."
            % {"value": profile_set, "allowed": ", ".join(sorted(profile_data))}
        )

    profiles = get_config_profiles(api, namespace)
    return validate_nodegroup_config_profile_set(
        profile_set,
        profile_data[profile_set],
        profiles,
    )


def kubelet_config_from_profile_defaults(
    profile_defaults: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    kubelet_fields = _get_config_profile_kubelet_fields(profile_defaults)
    config_yaml = _render_kubelet_config_yaml(kubelet_fields)

    return {
        "enabled": bool(kubelet_fields),
        "configYaml": config_yaml,
    }


def _render_kubelet_config_yaml(
    profile_defaults: typing.Dict[str, typing.Any],
) -> str:
    if not profile_defaults:
        return ""

    config_yaml = yaml.safe_dump(
        profile_defaults,
        default_flow_style=False,
        sort_keys=True,
    ).rstrip()
    lines = config_yaml.splitlines()
    if not lines:
        return ""

    return "\n".join([lines[0], *[f"  {line}" for line in lines[1:]]])


def get_kubelet_config(
    cluster: magnum_objects.Cluster,
    api: pykube.HTTPClient | None = None,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Any]:
    return get_config_profile(cluster, api, namespace)["kubeletConfig"]


def config_profile_from_profile_defaults(
    profile_defaults: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    kubelet_config = kubelet_config_from_profile_defaults(profile_defaults)
    files_yaml = [
        _render_config_profile_yaml(_normalise_config_profile_file(entry))
        for entry in _get_config_profile_list(
            profile_defaults,
            "files",
            CONFIG_PROFILE_MAX_FILES,
        )
    ]
    pre_kubeadm_commands = _get_config_profile_commands(
        profile_defaults,
        "preKubeadmCommands",
        CONFIG_PROFILE_MAX_PRE_COMMANDS,
    )
    post_kubeadm_commands = _get_config_profile_commands(
        profile_defaults,
        "postKubeadmCommands",
        CONFIG_PROFILE_MAX_POST_COMMANDS,
    )

    return {
        "enabled": bool(
            kubelet_config["enabled"]
            or files_yaml
            or pre_kubeadm_commands
            or post_kubeadm_commands
        ),
        "kubeletConfig": kubelet_config,
        "filesYaml": files_yaml,
        "preKubeadmCommands": pre_kubeadm_commands,
        "postKubeadmCommands": post_kubeadm_commands,
    }


def get_config_profile(
    cluster: magnum_objects.Cluster,
    api: pykube.HTTPClient | None = None,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Any]:
    profile = cluster.labels.get("config_profile", "")
    profile_defaults = get_config_profile_defaults(
        profile,
        api,
        namespace,
    )
    return config_profile_from_profile_defaults(profile_defaults)


def get_nodegroup_kubelet_config(
    cluster: magnum_objects.Cluster,
    nodegroup: magnum_objects.NodeGroup,
    api: pykube.HTTPClient | None = None,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Any] | None:
    config_profile = get_nodegroup_config_profile(cluster, nodegroup, api, namespace)
    if config_profile is None:
        return None
    return config_profile["kubeletConfig"]


def get_nodegroup_config_profile(
    cluster: magnum_objects.Cluster,
    nodegroup: magnum_objects.NodeGroup,
    api: pykube.HTTPClient | None = None,
    namespace: str = "magnum-system",
) -> typing.Dict[str, typing.Any] | None:
    profile_set = get_nodegroup_config_profile_set(
        cluster.labels.get("nodegroup_config_profile_set", ""),
        api,
        namespace,
    )
    nodegroup_config = profile_set.get(nodegroup.name)
    if nodegroup_config is None:
        return None

    return config_profile_from_profile_defaults(
        get_config_profile_defaults(
            nodegroup_config["profile"],
            api,
            namespace,
        )
    )


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


def validate_cluster(
    ctx: context.RequestContext,
    cluster: magnum_objects.Cluster,
    api: pykube.HTTPClient | None = None,
):
    # Check network driver
    if cluster.cluster_template.network_driver not in ["cilium", "calico"]:
        raise mcapi_exceptions.UnsupportedCNI

    validate_config_profile_labels(cluster, api)

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
