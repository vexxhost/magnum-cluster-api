# Copyright (c) 2026 VEXXHOST, Inc.
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

import dataclasses
import hashlib
import json
import re
import typing
import uuid

import pykube  # type: ignore
import yaml
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import exception  # type: ignore

MACHINE_NETWORK_PROFILE_LABEL = "machine_network_profile"
MACHINE_NETWORK_PROFILES_CONFIGMAP = "mcapi-machine-network-profiles"
MACHINE_NETWORK_PROFILES_CONFIGMAP_KEY = "profiles.yaml"
NETWORK_ANNOTATION_PREFIX = "network.magnum-cluster-api.openstack.org/"
PROFILE_ANNOTATION = f"{NETWORK_ANNOTATION_PREFIX}profile"
CONTRACT_ANNOTATION = f"{NETWORK_ANNOTATION_PREFIX}contract"
CONTRACT_SHA256_ANNOTATION = f"{NETWORK_ANNOTATION_PREFIX}contract-sha256"
CAPABILITIES_ANNOTATION = f"{NETWORK_ANNOTATION_PREFIX}capabilities"

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024
MAX_CONTRACT_BYTES = 64 * 1024
MAX_PROFILES = 16
MAX_PORTS = 16
MAX_FIXED_IPS = 4
MAX_CAPABILITIES = 32

_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
_QUALIFIED_NAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[-a-z0-9]*[a-z0-9])?\.)+"
    r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?/"
    r"[A-Za-z0-9](?:[-_.A-Za-z0-9]*[A-Za-z0-9])?$"
)
_TARGETS = {"all", "control-plane", "workers"}
_NODEGROUP_PREFIX = "nodegroup:"
_PRIMARY_ROLE = "primary"


@dataclasses.dataclass(frozen=True)
class FixedIP:
    subnet_id: str


@dataclasses.dataclass(frozen=True)
class AdditionalPort:
    role: str
    network_id: str
    fixed_ips: tuple[FixedIP, ...]
    vnic_type: str | None
    port_security_enabled: bool | None


@dataclasses.dataclass(frozen=True)
class MachineNetworkSelection:
    name: str
    applies_to: str
    provides_capabilities: tuple[str, ...]
    additional_ports: tuple[AdditionalPort, ...]
    contract: str
    digest: str

    def applies_to_control_plane(self) -> bool:
        return self.applies_to in {"all", "control-plane"}

    def applies_to_nodegroup(self, name: str) -> bool:
        return self.applies_to in {"all", "workers"} or self.applies_to == (
            f"{_NODEGROUP_PREFIX}{name}"
        )


def _invalid(message: str) -> exception.Invalid:
    return exception.Invalid(message)


def _dns_label(value: typing.Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 63
        or _DNS_LABEL_RE.fullmatch(value) is None
    ):
        raise _invalid(f"Invalid {field}: expected a DNS label.")
    return value


def _uuid(value: typing.Any, field: str) -> str:
    if not isinstance(value, str):
        raise _invalid(f"Invalid {field}: expected a UUID string.")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise _invalid(f"Invalid {field}: expected a UUID string.")
    return str(parsed)


def _capabilities(value: typing.Any, profile: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_CAPABILITIES:
        raise _invalid(
            f"Invalid providesCapabilities in machine network profile {profile}: "
            f"expected at most {MAX_CAPABILITIES} unique strings."
        )
    result: list[str] = []
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 253
            or _QUALIFIED_NAME_RE.fullmatch(item) is None
            or item in result
        ):
            raise _invalid(
                f"Invalid capability {item!r} in machine network profile {profile}."
            )
        result.append(item)
    return tuple(sorted(result))


def _applies_to(value: typing.Any, profile: str) -> str:
    if value in _TARGETS:
        return typing.cast(str, value)
    if isinstance(value, str) and value.startswith(_NODEGROUP_PREFIX):
        _dns_label(value[len(_NODEGROUP_PREFIX) :], f"appliesTo in {profile}")
        return value
    raise _invalid(
        f"Invalid appliesTo in machine network profile {profile}: expected all, "
        "control-plane, workers, or nodegroup:<name>."
    )


def _fixed_ips(value: typing.Any, profile: str, role: str) -> tuple[FixedIP, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_FIXED_IPS:
        raise _invalid(
            f"Invalid fixedIPs for port {role} in machine network profile {profile}."
        )
    result: list[FixedIP] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"subnetID"}:
            raise _invalid(
                f"Invalid fixedIPs for port {role} in machine network profile {profile}: "
                "schema version 1 accepts only subnetID."
            )
        fixed_ip = FixedIP(_uuid(item["subnetID"], f"subnetID for port {role}"))
        if fixed_ip in result:
            raise _invalid(
                f"Duplicate subnetID for port {role} in machine network profile {profile}."
            )
        result.append(fixed_ip)
    return tuple(result)


def _port(value: typing.Any, profile: str) -> AdditionalPort:
    if not isinstance(value, dict):
        raise _invalid(f"Invalid additional port in machine network profile {profile}.")
    allowed = {
        "role",
        "networkID",
        "fixedIPs",
        "vnicType",
        "portSecurityEnabled",
    }
    unknown = set(value) - allowed
    missing = {"role", "networkID"} - set(value)
    if unknown or missing:
        field = sorted(unknown or missing)[0]
        action = "unsupported" if unknown else "missing"
        raise _invalid(
            f"Invalid additional port in machine network profile {profile}: "
            f"{action} field {field}."
        )
    role = _dns_label(value["role"], f"port role in {profile}")
    if role == _PRIMARY_ROLE:
        raise _invalid(f"Port role {_PRIMARY_ROLE} is reserved in profile {profile}.")
    vnic_type = value.get("vnicType")
    if vnic_type is not None and (
        not isinstance(vnic_type, str) or not vnic_type or len(vnic_type) > 64
    ):
        raise _invalid(f"Invalid vnicType for port {role} in profile {profile}.")
    port_security_enabled = value.get("portSecurityEnabled")
    if port_security_enabled is not None and not isinstance(
        port_security_enabled, bool
    ):
        raise _invalid(
            f"Invalid portSecurityEnabled for port {role} in profile {profile}."
        )
    return AdditionalPort(
        role=role,
        network_id=_uuid(value["networkID"], f"networkID for port {role}"),
        fixed_ips=_fixed_ips(value.get("fixedIPs"), profile, role),
        vnic_type=vnic_type,
        port_security_enabled=port_security_enabled,
    )


def _parse_profile(name: str, value: typing.Any) -> dict[str, typing.Any]:
    _dns_label(name, "machine network profile name")
    if not isinstance(value, dict):
        raise _invalid(f"Invalid machine network profile {name}: expected an object.")
    allowed = {
        "mode",
        "appliesTo",
        "providesCapabilities",
        "additionalPorts",
    }
    required = allowed
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        field = sorted(unknown or missing)[0]
        action = "unsupported" if unknown else "missing"
        raise _invalid(
            f"Invalid machine network profile {name}: {action} field {field}."
        )
    if value["mode"] != "augment":
        raise _invalid(
            f"Invalid mode in machine network profile {name}: schema version 1 "
            "supports only augment."
        )
    raw_ports = value["additionalPorts"]
    if not isinstance(raw_ports, list) or not raw_ports or len(raw_ports) > MAX_PORTS:
        raise _invalid(
            f"Invalid additionalPorts in machine network profile {name}: expected "
            f"between 1 and {MAX_PORTS} ports."
        )
    ports = tuple(_port(item, name) for item in raw_ports)
    roles = [port.role for port in ports]
    if len(set(roles)) != len(roles):
        raise _invalid(f"Duplicate port role in machine network profile {name}.")
    identities = [
        (port.network_id, tuple(item.subnet_id for item in port.fixed_ips))
        for port in ports
    ]
    if len(set(identities)) != len(identities):
        raise _invalid(f"Duplicate network and subnet selection in profile {name}.")
    return {
        "name": name,
        "applies_to": _applies_to(value["appliesTo"], name),
        "provides_capabilities": _capabilities(value["providesCapabilities"], name),
        "additional_ports": ports,
    }


def _canonical_port(port: AdditionalPort) -> dict[str, typing.Any]:
    result: dict[str, typing.Any] = {
        "fixedIPs": [{"subnetID": item.subnet_id} for item in port.fixed_ips],
        "networkID": port.network_id,
        "portSecurityEnabled": port.port_security_enabled,
        "role": port.role,
        "vnicType": port.vnic_type,
    }
    return result


def _selection(name: str, value: typing.Any) -> MachineNetworkSelection:
    parsed = _parse_profile(name, value)
    contract_object = {
        "additionalPorts": [
            _canonical_port(port) for port in parsed["additional_ports"]
        ],
        "appliesTo": parsed["applies_to"],
        "mode": "augment",
        "name": name,
        "providesCapabilities": list(parsed["provides_capabilities"]),
        "schemaVersion": SCHEMA_VERSION,
    }
    contract = json.dumps(
        contract_object, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    if len(contract.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise _invalid(
            f"Resolved machine network contract exceeds {MAX_CONTRACT_BYTES} bytes."
        )
    return MachineNetworkSelection(
        contract=contract,
        digest=hashlib.sha256(contract.encode("utf-8")).hexdigest(),
        **parsed,
    )


def get_profiles(
    api: pykube.HTTPClient, namespace: str = "magnum-system"
) -> dict[str, typing.Any]:
    config_map = pykube.ConfigMap.objects(api, namespace=namespace).get_or_none(
        name=MACHINE_NETWORK_PROFILES_CONFIGMAP
    )
    if config_map is None:
        return {}
    raw = config_map.obj.get("data", {}).get(MACHINE_NETWORK_PROFILES_CONFIGMAP_KEY)
    if raw is None:
        raise _invalid(
            f"ConfigMap {namespace}/{MACHINE_NETWORK_PROFILES_CONFIGMAP} is missing "
            f"{MACHINE_NETWORK_PROFILES_CONFIGMAP_KEY}."
        )
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _invalid(
            f"Invalid machine network profile document: maximum is {MAX_DOCUMENT_BYTES} bytes."
        )
    try:
        document = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise _invalid(f"Invalid machine network profile YAML: {exc}.")
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion",
        "profiles",
    }:
        raise _invalid(
            "Invalid machine network profile document: expected only schemaVersion and profiles."
        )
    if document["schemaVersion"] != SCHEMA_VERSION:
        raise _invalid(
            f"Invalid machine network profile schemaVersion: expected {SCHEMA_VERSION}."
        )
    profiles = document["profiles"]
    if not isinstance(profiles, dict) or len(profiles) > MAX_PROFILES:
        raise _invalid(
            f"Invalid machine network profiles: expected at most {MAX_PROFILES} profiles."
        )
    for name, value in profiles.items():
        _parse_profile(name, value)
    return profiles


def prepare_cluster(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> MachineNetworkSelection | None:
    template_labels = getattr(cluster.cluster_template, "labels", None) or {}
    cluster_labels = cluster.labels or {}
    requested = cluster_labels.get(MACHINE_NETWORK_PROFILE_LABEL)
    selected = template_labels.get(MACHINE_NETWORK_PROFILE_LABEL)
    if requested is not None and requested != selected:
        raise _invalid(
            f"Invalid value for {MACHINE_NETWORK_PROFILE_LABEL}: {requested}. This "
            "label must be set on the cluster template and cannot be overridden "
            "during cluster creation."
        )
    if selected is None:
        if cluster.labels is not None:
            cluster.labels.pop(MACHINE_NETWORK_PROFILE_LABEL, None)
        return None
    _dns_label(selected, MACHINE_NETWORK_PROFILE_LABEL)
    profiles = get_profiles(api)
    if selected not in profiles:
        raise _invalid(f"Machine network profile {selected} does not exist.")
    selection = _selection(selected, profiles[selected])
    if cluster.labels is None:
        cluster.labels = {}
    cluster.labels[MACHINE_NETWORK_PROFILE_LABEL] = selected
    validate_target(selection, cluster)
    return selection


def resolve_selection(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> MachineNetworkSelection | None:
    selected = (cluster.labels or {}).get(MACHINE_NETWORK_PROFILE_LABEL)
    if selected is None:
        return None
    profiles = get_profiles(api)
    if selected not in profiles:
        raise _invalid(f"Machine network profile {selected} does not exist.")
    selection = _selection(selected, profiles[selected])
    validate_target(selection, cluster)
    return selection


def validate_target(
    selection: MachineNetworkSelection, cluster: magnum_objects.Cluster
) -> None:
    if not selection.applies_to.startswith(_NODEGROUP_PREFIX):
        return
    target = selection.applies_to[len(_NODEGROUP_PREFIX) :]
    workers = {
        nodegroup.name
        for nodegroup in cluster.nodegroups
        if nodegroup.role != "master"
        and not str(nodegroup.status or "").startswith("DELETE")
    }
    if target not in workers:
        raise _invalid(
            f"Machine network profile {selection.name} targets unknown worker "
            f"node group {target}."
        )


def selection_from_cluster(capi_cluster) -> MachineNetworkSelection | None:
    annotations = capi_cluster.obj.get("metadata", {}).get("annotations", {})
    name = annotations.get(PROFILE_ANNOTATION)
    raw = annotations.get(CONTRACT_ANNOTATION)
    digest = annotations.get(CONTRACT_SHA256_ANNOTATION)
    capabilities = annotations.get(CAPABILITIES_ANNOTATION)
    if all(item is None for item in (name, raw, digest, capabilities)):
        return None
    if not all(isinstance(item, str) for item in (name, raw, digest, capabilities)):
        raise _invalid(
            "Incomplete machine network profile snapshot on Cluster API Cluster."
        )
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != digest:
        raise _invalid("Machine network profile snapshot digest does not match.")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _invalid(f"Invalid machine network profile snapshot: {exc}.")
    if not isinstance(document, dict) or set(document) != {
        "additionalPorts",
        "appliesTo",
        "mode",
        "name",
        "providesCapabilities",
        "schemaVersion",
    }:
        raise _invalid("Invalid machine network profile snapshot fields.")
    if document["schemaVersion"] != SCHEMA_VERSION or document["name"] != name:
        raise _invalid("Machine network profile snapshot identity does not match.")
    profile = {
        "mode": document["mode"],
        "appliesTo": document["appliesTo"],
        "providesCapabilities": document["providesCapabilities"],
        "additionalPorts": document["additionalPorts"],
    }
    restored = _selection(name, profile)
    if restored.contract != raw or restored.digest != digest:
        raise _invalid("Machine network profile snapshot is not canonical.")
    if "+".join(restored.provides_capabilities) != capabilities:
        raise _invalid(
            "Machine network profile capabilities do not match the snapshot."
        )
    return restored


def cluster_metadata(
    selection: MachineNetworkSelection | None,
) -> dict[str, str]:
    if selection is None:
        return {}
    return {
        PROFILE_ANNOTATION: selection.name,
        CONTRACT_ANNOTATION: selection.contract,
        CONTRACT_SHA256_ANNOTATION: selection.digest,
        CAPABILITIES_ANNOTATION: "+".join(selection.provides_capabilities),
    }


def render_machine_ports(
    selection: MachineNetworkSelection,
    fixed_network_id: str,
    fixed_subnet_id: str | None,
) -> list[dict[str, typing.Any]]:
    if not fixed_network_id:
        raise _invalid(
            f"Machine network profile {selection.name} requires an existing fixed "
            "primary network because CAPO ports replace its default machine port."
        )
    primary: dict[str, typing.Any] = {
        "nameSuffix": _PRIMARY_ROLE,
        "network": {"id": _uuid(fixed_network_id, "fixed primary network")},
    }
    if fixed_subnet_id:
        primary["fixedIPs"] = [
            {"subnet": {"id": _uuid(fixed_subnet_id, "fixed primary subnet")}}
        ]
    rendered = [primary]
    for port in selection.additional_ports:
        item: dict[str, typing.Any] = {
            "nameSuffix": port.role,
            "network": {"id": port.network_id},
        }
        if port.fixed_ips:
            item["fixedIPs"] = [
                {"subnet": {"id": fixed_ip.subnet_id}} for fixed_ip in port.fixed_ips
            ]
        if port.vnic_type is not None:
            item["vnicType"] = port.vnic_type
        if port.port_security_enabled is not None:
            item["disablePortSecurity"] = not port.port_security_enabled
        rendered.append(item)
    identities = [
        (
            item["network"]["id"],
            tuple(fixed_ip["subnet"]["id"] for fixed_ip in item.get("fixedIPs", [])),
        )
        for item in rendered
    ]
    if len(set(identities)) != len(identities):
        raise _invalid(
            f"Machine network profile {selection.name} duplicates the primary network "
            "and subnet selection."
        )
    return rendered
