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
import datetime
import hashlib
import json
import re
import typing

import pykube  # type: ignore
import yaml
from magnum import objects as magnum_objects  # type: ignore
from magnum.common import exception  # type: ignore

from magnum_cluster_api import objects

ADDON_PROFILES_LABEL = "addon_profiles"
ADDON_PROFILES_CONFIGMAP = "mcapi-addon-profiles"
ADDON_PROFILES_CONFIGMAP_KEY = "profiles.yaml"
ADDON_LABEL_PREFIX = "addons.magnum-cluster-api.openstack.org/"
SELECTED_PROFILES_ANNOTATION = f"{ADDON_LABEL_PREFIX}selected-profiles"
PROFILES_CONTRACT_ANNOTATION = f"{ADDON_LABEL_PREFIX}profiles-contract"
PROFILES_CONTRACT_SHA256_ANNOTATION = f"{ADDON_LABEL_PREFIX}profiles-contract-sha256"
CREATE_STARTED_ANNOTATION = f"{ADDON_LABEL_PREFIX}profiles-create-started"
DELETE_STARTED_ANNOTATION = f"{ADDON_LABEL_PREFIX}profiles-delete-started"

CAPI_CLUSTER_NAME_LABEL = "cluster.x-k8s.io/cluster-name"
HELM_CHART_PROXY_LABEL = "helmreleaseproxy.addons.cluster.x-k8s.io/helmchartproxy-name"
INSTALL_ONCE_RECONCILE_STRATEGY = "InstallOnce"
HELM_RELEASE_PROXY_FINALIZER = "helmreleaseproxy.addons.cluster.x-k8s.io"

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024
MAX_CONTRACT_BYTES = 128 * 1024
MAX_PROFILES = 16
MAX_DEPENDENCIES = 16
MAX_LABELS_PER_PROFILE = 16
MAX_CAPABILITIES_PER_PROFILE = 32

_UNSUPPORTED_ADDON_PROFILE_LABEL = "addon_profile"
_DURATION_RE = re.compile(r"^(?P<value>[1-9][0-9]*)(?P<unit>[smh])$")
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
_LABEL_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[-_.A-Za-z0-9]*[A-Za-z0-9])?$")
_QUALIFIED_NAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[-a-z0-9]*[a-z0-9])?\.)+"
    r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?/"
    r"[A-Za-z0-9](?:[-_.A-Za-z0-9]*[A-Za-z0-9])?$"
)
_REPORTED_CREATE_REASONS = {
    "GetCACertificateFailed",
    "GetClusterFailed",
    "GetCredentialsFailed",
    "GetKubeconfigFailed",
    "HelmInstallOrUpgradeFailed",
    "HelmReleaseGetFailed",
}
_TERMINAL_DELETE_REASONS = {"HelmReleaseDeletionFailed"}


@dataclasses.dataclass(frozen=True)
class AddonProfile:
    name: str
    category: str | None
    depends_on: tuple[str, ...]
    requires_capabilities: tuple[str, ...]
    cluster_labels: dict[str, str]
    required_helm_chart_proxy: str
    release_name: str
    create_timeout: datetime.timedelta
    delete_timeout: datetime.timedelta


@dataclasses.dataclass(frozen=True)
class AddonSelection:
    profiles: tuple[AddonProfile, ...]
    waves: tuple[tuple[str, ...], ...]
    contract: str
    digest: str

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(profile.name for profile in self.profiles)

    def profile(self, name: str) -> AddonProfile:
        return next(profile for profile in self.profiles if profile.name == name)


@dataclasses.dataclass(frozen=True)
class GateResult:
    state: typing.Literal["ready", "waiting", "failed"]
    reason: str


def _invalid(message: str) -> exception.Invalid:
    return exception.Invalid(message)


def _parse_duration(value: typing.Any, field: str, profile: str) -> datetime.timedelta:
    if not isinstance(value, str):
        raise _invalid(
            f"Invalid {field} in add-on profile {profile}: expected a duration string."
        )
    match = _DURATION_RE.fullmatch(value)
    if match is None:
        raise _invalid(
            f"Invalid {field} in add-on profile {profile}: expected a positive "
            "integer followed by s, m, or h."
        )
    unit = match.group("unit")
    seconds = int(match.group("value")) * {"s": 1, "m": 60, "h": 3600}[unit]
    if seconds > 24 * 60 * 60:
        raise _invalid(f"Invalid {field} in add-on profile {profile}: maximum is 24h.")
    return datetime.timedelta(seconds=seconds)


def _format_duration(value: datetime.timedelta) -> str:
    return f"{int(value.total_seconds())}s"


def _validate_dns_label(value: typing.Any, field: str, profile: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 63
        or _DNS_LABEL_RE.fullmatch(value) is None
    ):
        raise _invalid(
            f"Invalid {field} in add-on profile {profile}: expected a DNS label."
        )
    return value


def _validate_string_list(
    value: typing.Any,
    field: str,
    profile: str,
    *,
    maximum: int,
    qualified: bool = False,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > maximum:
        raise _invalid(
            f"Invalid {field} in add-on profile {profile}: expected at most "
            f"{maximum} unique strings."
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or item in result:
            raise _invalid(
                f"Invalid {field} in add-on profile {profile}: values must be "
                "non-empty and unique."
            )
        if qualified:
            if len(item) > 253 or _QUALIFIED_NAME_RE.fullmatch(item) is None:
                raise _invalid(
                    f"Invalid capability {item!r} in add-on profile {profile}."
                )
        else:
            _validate_dns_label(item, field, profile)
        result.append(item)
    return tuple(result)


def _validate_cluster_labels(value: typing.Any, profile: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value or len(value) > MAX_LABELS_PER_PROFILE:
        raise _invalid(
            f"Invalid clusterLabels in add-on profile {profile}: expected a "
            f"non-empty mapping with at most {MAX_LABELS_PER_PROFILE} entries."
        )

    labels: dict[str, str] = {}
    for key, label_value in value.items():
        if not isinstance(key, str) or not key.startswith(ADDON_LABEL_PREFIX):
            raise _invalid(
                f"Invalid cluster label {key!r} in add-on profile {profile}: "
                f"keys must start with {ADDON_LABEL_PREFIX}."
            )
        name = key.rsplit("/", 1)[-1]
        if len(name) > 63 or _LABEL_NAME_RE.fullmatch(name) is None:
            raise _invalid(
                f"Invalid cluster label {key!r} in add-on profile {profile}."
            )
        if not isinstance(label_value, str) or len(label_value) > 63:
            raise _invalid(
                f"Invalid value for cluster label {key!r} in add-on profile {profile}."
            )
        if label_value and _LABEL_NAME_RE.fullmatch(label_value) is None:
            raise _invalid(
                f"Invalid value for cluster label {key!r} in add-on profile {profile}."
            )
        labels[key] = label_value
    return labels


def _parse_profile(name: str, value: typing.Any) -> AddonProfile:
    _validate_dns_label(name, "profile name", name)
    if not isinstance(value, dict):
        raise _invalid(f"Invalid add-on profile {name}: expected a YAML object.")

    allowed = {
        "category",
        "dependsOn",
        "requiresCapabilities",
        "clusterLabels",
        "requiredHelmChartProxy",
        "releaseName",
        "createTimeout",
        "deleteTimeout",
    }
    required = {
        "clusterLabels",
        "requiredHelmChartProxy",
        "releaseName",
        "createTimeout",
        "deleteTimeout",
    }
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise _invalid(
            f"Invalid add-on profile {name}: unsupported field {sorted(unknown)[0]}."
        )
    if missing:
        raise _invalid(
            f"Invalid add-on profile {name}: missing field {sorted(missing)[0]}."
        )

    category = value.get("category")
    if category is not None:
        category = _validate_dns_label(category, "category", name)
    return AddonProfile(
        name=name,
        category=category,
        depends_on=_validate_string_list(
            value.get("dependsOn", []), "dependsOn", name, maximum=MAX_DEPENDENCIES
        ),
        requires_capabilities=_validate_string_list(
            value.get("requiresCapabilities", []),
            "requiresCapabilities",
            name,
            maximum=MAX_CAPABILITIES_PER_PROFILE,
            qualified=True,
        ),
        cluster_labels=_validate_cluster_labels(value["clusterLabels"], name),
        required_helm_chart_proxy=_validate_dns_label(
            value["requiredHelmChartProxy"], "requiredHelmChartProxy", name
        ),
        release_name=_validate_dns_label(value["releaseName"], "releaseName", name),
        create_timeout=_parse_duration(value["createTimeout"], "createTimeout", name),
        delete_timeout=_parse_duration(value["deleteTimeout"], "deleteTimeout", name),
    )


def get_profiles(
    api: pykube.HTTPClient, namespace: str = "magnum-system"
) -> dict[str, AddonProfile]:
    config_map = pykube.ConfigMap.objects(api, namespace=namespace).get_or_none(
        name=ADDON_PROFILES_CONFIGMAP
    )
    if config_map is None:
        return {}

    raw = config_map.obj.get("data", {}).get(ADDON_PROFILES_CONFIGMAP_KEY)
    if raw is None:
        raise _invalid(
            f"ConfigMap {namespace}/{ADDON_PROFILES_CONFIGMAP} is missing "
            f"{ADDON_PROFILES_CONFIGMAP_KEY}."
        )
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _invalid(
            f"Invalid add-on profile document: maximum is {MAX_DOCUMENT_BYTES} bytes."
        )
    try:
        document = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise _invalid(f"Invalid add-on profile YAML: {exc}.")
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion",
        "profiles",
    }:
        raise _invalid(
            "Invalid add-on profile document: expected only schemaVersion and profiles."
        )
    if document["schemaVersion"] != SCHEMA_VERSION:
        raise _invalid(
            f"Invalid add-on profile schemaVersion: expected {SCHEMA_VERSION}."
        )
    if not isinstance(document["profiles"], dict):
        raise _invalid("Invalid add-on profile document: profiles must be a mapping.")
    if len(document["profiles"]) > MAX_PROFILES:
        raise _invalid(
            f"Invalid add-on profile document: maximum is {MAX_PROFILES} profiles."
        )

    profiles = {
        name: _parse_profile(name, value)
        for name, value in document["profiles"].items()
    }
    _validate_catalog(profiles)
    return profiles


def _validate_catalog(profiles: dict[str, AddonProfile]) -> None:
    label_owners: dict[str, str] = {}
    hcp_owners: dict[str, str] = {}
    for profile in profiles.values():
        if profile.name in profile.depends_on:
            raise _invalid(f"Add-on profile {profile.name} cannot depend on itself.")
        for dependency in profile.depends_on:
            if dependency not in profiles:
                raise _invalid(
                    f"Add-on profile {profile.name} depends on missing profile {dependency}."
                )
        for label in profile.cluster_labels:
            if label in label_owners:
                raise _invalid(
                    f"Cluster label {label} is owned by both {label_owners[label]} "
                    f"and {profile.name}."
                )
            label_owners[label] = profile.name
        hcp = profile.required_helm_chart_proxy
        if hcp in hcp_owners:
            raise _invalid(
                f"HelmChartProxy {hcp} is required by both {hcp_owners[hcp]} and "
                f"{profile.name}."
            )
        hcp_owners[hcp] = profile.name

    _dependency_waves(tuple(profiles), profiles)


def _parse_selector(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise _invalid(f"Invalid value for {ADDON_PROFILES_LABEL}: expected profiles.")
    names = value.split("+")
    if len(names) > MAX_PROFILES:
        raise _invalid(
            f"Invalid value for {ADDON_PROFILES_LABEL}: maximum is {MAX_PROFILES}."
        )
    if any(not name or name.strip() != name for name in names):
        raise _invalid(
            f"Invalid value for {ADDON_PROFILES_LABEL}: empty entries and whitespace "
            "are not allowed."
        )
    if len(set(names)) != len(names):
        raise _invalid(f"Invalid value for {ADDON_PROFILES_LABEL}: duplicate profile.")
    for name in names:
        _validate_dns_label(name, ADDON_PROFILES_LABEL, name)
    return tuple(names)


def _dependency_waves(
    selected: tuple[str, ...], profiles: dict[str, AddonProfile]
) -> tuple[tuple[str, ...], ...]:
    selected_set = set(selected)
    order = {name: index for index, name in enumerate(selected)}
    remaining = set(selected)
    completed: set[str] = set()
    waves: list[tuple[str, ...]] = []

    for name in selected:
        missing = set(profiles[name].depends_on) - selected_set
        if missing:
            raise _invalid(
                f"Add-on profile {name} requires unselected dependency "
                f"{sorted(missing)[0]}."
            )

    while remaining:
        wave = sorted(
            (name for name in remaining if set(profiles[name].depends_on) <= completed),
            key=lambda name: (order[name], name),
        )
        if not wave:
            raise _invalid("Add-on profile dependency graph contains a cycle.")
        waves.append(tuple(wave))
        completed.update(wave)
        remaining.difference_update(wave)
    return tuple(waves)


def _canonical_profile(profile: AddonProfile) -> dict[str, typing.Any]:
    return {
        "category": profile.category,
        "clusterLabels": dict(sorted(profile.cluster_labels.items())),
        "createTimeout": _format_duration(profile.create_timeout),
        "deleteTimeout": _format_duration(profile.delete_timeout),
        "dependsOn": list(profile.depends_on),
        "releaseName": profile.release_name,
        "requiredHelmChartProxy": profile.required_helm_chart_proxy,
        "requiresCapabilities": sorted(profile.requires_capabilities),
    }


def _selection(
    names: tuple[str, ...], profiles: dict[str, AddonProfile]
) -> AddonSelection:
    missing = [name for name in names if name not in profiles]
    if missing:
        raise _invalid(f"Add-on profile {missing[0]} does not exist.")
    selected_profiles = tuple(profiles[name] for name in names)
    waves = _dependency_waves(names, profiles)
    contract_object = {
        "profiles": {
            profile.name: _canonical_profile(profile) for profile in selected_profiles
        },
        "schemaVersion": SCHEMA_VERSION,
        "selectedProfiles": list(names),
        "waves": [list(wave) for wave in waves],
    }
    contract = json.dumps(
        contract_object, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    if len(contract.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise _invalid(
            f"Resolved add-on profile contract exceeds {MAX_CONTRACT_BYTES} bytes."
        )
    digest = hashlib.sha256(contract.encode("utf-8")).hexdigest()
    return AddonSelection(selected_profiles, waves, contract, digest)


def _reject_unsupported_selector(labels: dict[str, str]) -> None:
    if _UNSUPPORTED_ADDON_PROFILE_LABEL in labels:
        raise _invalid(
            f"Unsupported label {_UNSUPPORTED_ADDON_PROFILE_LABEL}; use "
            f"{ADDON_PROFILES_LABEL}."
        )


def prepare_cluster(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> AddonSelection | None:
    """Inherit and validate the immutable template add-on selectors."""
    template_labels = getattr(cluster.cluster_template, "labels", None) or {}
    cluster_labels = cluster.labels or {}
    _reject_unsupported_selector(template_labels)
    _reject_unsupported_selector(cluster_labels)
    requested = cluster_labels.get(ADDON_PROFILES_LABEL)
    selected = template_labels.get(ADDON_PROFILES_LABEL)

    if requested is not None and requested != selected:
        raise _invalid(
            f"Invalid value for {ADDON_PROFILES_LABEL}: {requested}. This label "
            "must be set on the cluster template and cannot be overridden during "
            "cluster creation."
        )
    if selected is None:
        if cluster.labels is not None:
            cluster.labels.pop(ADDON_PROFILES_LABEL, None)
        return None

    names = _parse_selector(selected)
    profiles = get_profiles(api)
    selection = _selection(names, profiles)
    if cluster.labels is None:
        cluster.labels = {}
    cluster.labels[ADDON_PROFILES_LABEL] = selected
    return selection


def resolve_selection(
    api: pykube.HTTPClient, cluster: magnum_objects.Cluster
) -> AddonSelection | None:
    selected = (cluster.labels or {}).get(ADDON_PROFILES_LABEL)
    if selected is None:
        return None
    return _selection(_parse_selector(selected), get_profiles(api))


def selection_from_cluster(capi_cluster) -> AddonSelection | None:
    annotations = capi_cluster.obj.get("metadata", {}).get("annotations", {})
    raw = annotations.get(PROFILES_CONTRACT_ANNOTATION)
    digest = annotations.get(PROFILES_CONTRACT_SHA256_ANNOTATION)
    selected = annotations.get(SELECTED_PROFILES_ANNOTATION)
    if raw is None and digest is None and selected is None:
        return None
    if not all(isinstance(item, str) and item for item in (raw, digest, selected)):
        raise _invalid("Incomplete add-on profile snapshot on Cluster API Cluster.")
    actual_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if actual_digest != digest:
        raise _invalid("Add-on profile snapshot digest does not match its contract.")
    try:
        document = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise _invalid(f"Invalid add-on profile snapshot: {exc}.")
    if not isinstance(document, dict) or set(document) != {
        "profiles",
        "schemaVersion",
        "selectedProfiles",
        "waves",
    }:
        raise _invalid("Invalid add-on profile snapshot fields.")
    if document["schemaVersion"] != SCHEMA_VERSION:
        raise _invalid("Unsupported add-on profile snapshot schemaVersion.")
    selected_profiles = document["selectedProfiles"]
    if not isinstance(selected_profiles, list) or not all(
        isinstance(name, str) for name in selected_profiles
    ):
        raise _invalid("Invalid selectedProfiles in add-on profile snapshot.")
    names = tuple(selected_profiles)
    if not names:
        raise _invalid("Invalid selectedProfiles in add-on profile snapshot.")
    if "+".join(names) != selected:
        raise _invalid("Selected add-on profiles do not match the snapshot.")
    profile_values = document["profiles"]
    if not isinstance(profile_values, dict):
        raise _invalid("Invalid profiles in add-on profile snapshot.")
    profiles = {
        name: _parse_profile(name, value) for name, value in profile_values.items()
    }
    _validate_catalog(profiles)
    restored = _selection(names, profiles)
    if restored.contract != raw or restored.digest != digest:
        raise _invalid("Add-on profile snapshot is not canonical.")
    return restored


def cluster_metadata(
    selection: AddonSelection | None,
) -> tuple[dict[str, str], dict[str, str]]:
    if selection is None:
        return {}, {}
    return {}, {
        SELECTED_PROFILES_ANNOTATION: "+".join(selection.names),
        PROFILES_CONTRACT_ANNOTATION: selection.contract,
        PROFILES_CONTRACT_SHA256_ANNOTATION: selection.digest,
    }


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _format_timestamp(value: datetime.datetime) -> str:
    return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(f"Invalid add-on lifecycle timestamp {value}: {exc}.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _timestamp_map(capi_cluster, annotation: str) -> dict[str, str]:
    raw = capi_cluster.obj.get("metadata", {}).get("annotations", {}).get(annotation)
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _invalid(f"Invalid add-on lifecycle timestamp map: {exc}.")
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise _invalid("Invalid add-on lifecycle timestamp map.")
    return value


def _updated_timestamp_map(
    capi_cluster, annotation: str, names: tuple[str, ...], *, reset: bool = False
) -> str:
    timestamps = {} if reset else _timestamp_map(capi_cluster, annotation)
    for name in names:
        if name not in timestamps:
            timestamps[name] = _format_timestamp(_now())
    return json.dumps(timestamps, sort_keys=True, separators=(",", ":"))


def _started(capi_cluster, annotation: str, profile: str) -> datetime.datetime:
    value = _timestamp_map(capi_cluster, annotation).get(profile)
    if value is None:
        raise _invalid(f"Missing lifecycle timestamp for add-on profile {profile}.")
    return _parse_timestamp(value)


def _patch_lifecycle_metadata(
    capi_cluster,
    *,
    annotations: dict[str, str],
    labels: dict[str, str | None],
) -> bool:
    metadata: dict[str, typing.Any] = {
        "annotations": annotations,
        "labels": labels,
    }
    resource_version = capi_cluster.obj.get("metadata", {}).get("resourceVersion")
    if resource_version is not None:
        metadata["resourceVersion"] = resource_version
    try:
        capi_cluster.patch({"metadata": metadata})
    except pykube.exceptions.HTTPError as exc:
        if exc.code != 409:
            raise
        capi_cluster.reload()
        return False
    return True


def _get_releases(
    api: pykube.HTTPClient, cluster_name: str, helm_chart_proxy: str
) -> list[objects.HelmReleaseProxy]:
    query = objects.HelmReleaseProxy.objects(api, namespace="magnum-system").filter(
        selector={
            CAPI_CLUSTER_NAME_LABEL: cluster_name,
            HELM_CHART_PROXY_LABEL: helm_chart_proxy,
        }
    )
    return list(query.all())


def _selector_matches(selector: dict, labels: dict[str, str]) -> bool:
    for key, value in selector.get("matchLabels", {}).items():
        if labels.get(key) != value:
            return False
    for expression in selector.get("matchExpressions", []):
        key = expression.get("key")
        operator = expression.get("operator")
        values = expression.get("values", [])
        if operator == "In" and labels.get(key) not in values:
            return False
        if operator == "NotIn" and labels.get(key) in values:
            return False
        if operator == "Exists" and key not in labels:
            return False
        if operator == "DoesNotExist" and key in labels:
            return False
        if operator not in {"In", "NotIn", "Exists", "DoesNotExist"}:
            return False
    return True


def _selector_uses_profile(selector: dict, profile: AddonProfile) -> bool:
    keys = set(selector.get("matchLabels", {}))
    keys.update(
        expression.get("key") for expression in selector.get("matchExpressions", [])
    )
    return bool(keys & set(profile.cluster_labels))


def _profile_chart_proxies(
    api: pykube.HTTPClient, capi_cluster, profile: AddonProfile
) -> list[objects.HelmChartProxy]:
    labels = capi_cluster.obj.get("metadata", {}).get("labels", {})
    proxies = objects.HelmChartProxy.objects(api, namespace="magnum-system").all()
    return [
        proxy
        for proxy in proxies
        if _selector_uses_profile(
            proxy.obj.get("spec", {}).get("clusterSelector", {}), profile
        )
        and _selector_matches(
            proxy.obj.get("spec", {}).get("clusterSelector", {}), labels
        )
    ]


def _release_condition(release: objects.HelmReleaseProxy) -> dict | None:
    return next(
        (
            condition
            for condition in release.obj.get("status", {}).get("conditions", [])
            if condition.get("type") == "Ready"
        ),
        None,
    )


def _terminal_condition(
    release: objects.HelmReleaseProxy, reasons: set[str]
) -> dict | None:
    generation = release.obj.get("metadata", {}).get("generation", 0)
    return next(
        (
            condition
            for condition in release.obj.get("status", {}).get("conditions", [])
            if condition.get("status") == "False"
            and condition.get("reason") in reasons
            and condition.get("observedGeneration", 0) >= generation
        ),
        None,
    )


def _release_identity_matches(
    release: objects.HelmReleaseProxy, profile: AddonProfile, cluster_name: str
) -> bool:
    spec = release.obj.get("spec", {})
    cluster_ref = spec.get("clusterRef", {})
    return (
        cluster_ref.get("name") == cluster_name
        and cluster_ref.get("namespace", "magnum-system") == "magnum-system"
        and spec.get("releaseName") == profile.release_name
    )


def _remove_caaph_finalizer(release: objects.HelmReleaseProxy) -> bool:
    metadata = release.obj.get("metadata", {})
    finalizers = metadata.get("finalizers", [])
    if HELM_RELEASE_PROXY_FINALIZER not in finalizers:
        return False
    release.patch(
        {
            "metadata": {
                "finalizers": [
                    item for item in finalizers if item != HELM_RELEASE_PROXY_FINALIZER
                ]
            }
        }
    )
    return True


def _profile_create_status(
    api: pykube.HTTPClient,
    capi_cluster,
    profile: AddonProfile,
    now: datetime.datetime,
) -> GateResult:
    started = _started(capi_cluster, CREATE_STARTED_ANNOTATION, profile.name)
    chart_proxies = _profile_chart_proxies(api, capi_cluster, profile)
    if len(chart_proxies) > 1:
        return GateResult(
            "failed", "Multiple HelmChartProxy resources match the add-on profile."
        )
    if not chart_proxies:
        if now - started >= profile.create_timeout:
            return GateResult("failed", "Timed out waiting for HelmChartProxy.")
        return GateResult(
            "waiting", "Waiting for HelmChartProxy to select the cluster."
        )
    if chart_proxies[0].name != profile.required_helm_chart_proxy:
        return GateResult(
            "failed",
            "The matching HelmChartProxy is not the profile-approved resource.",
        )

    releases = _get_releases(api, capi_cluster.name, profile.required_helm_chart_proxy)
    if len(releases) > 1:
        return GateResult(
            "failed",
            "Multiple HelmReleaseProxy resources match the required add-on release.",
        )
    if not releases:
        if now - started >= profile.create_timeout:
            return GateResult("failed", "Timed out waiting for HelmReleaseProxy.")
        return GateResult("waiting", "Waiting for HelmReleaseProxy to be created.")

    release = releases[0]
    if not _release_identity_matches(release, profile, capi_cluster.name):
        return GateResult(
            "failed", "HelmReleaseProxy identity does not match the add-on profile."
        )
    metadata = release.obj.get("metadata", {})
    status = release.obj.get("status", {})
    generation = metadata.get("generation", 0)
    condition = _release_condition(release)
    if (
        status.get("observedGeneration", 0) < generation
        or (condition or {}).get("observedGeneration", 0) < generation
    ):
        if now - started >= profile.create_timeout:
            return GateResult(
                "failed", "Timed out waiting for a current HelmReleaseProxy status."
            )
        return GateResult("waiting", "Waiting for current HelmReleaseProxy status.")
    if condition and condition.get("status") == "True":
        return GateResult("ready", "Required add-on release is Ready.")

    reported = _terminal_condition(release, _REPORTED_CREATE_REASONS)
    reason = (reported or condition or {}).get("reason", "Unknown")
    message = (reported or condition or {}).get(
        "message", "Helm release is reconciling."
    )
    if now - started >= profile.create_timeout:
        return GateResult(
            "failed", f"Timed out waiting for HelmReleaseProxy ({reason}): {message}"
        )
    return GateResult("waiting", f"HelmReleaseProxy {reason}: {message}")


def _activate_wave(capi_cluster, profiles: tuple[AddonProfile, ...]) -> bool:
    labels: dict[str, str] = {}
    for profile in profiles:
        labels.update(profile.cluster_labels)
    started = _updated_timestamp_map(
        capi_cluster, CREATE_STARTED_ANNOTATION, tuple(p.name for p in profiles)
    )
    if not _patch_lifecycle_metadata(
        capi_cluster,
        annotations={CREATE_STARTED_ANNOTATION: started},
        labels=labels,
    ):
        return False
    metadata = capi_cluster.obj.setdefault("metadata", {})
    metadata.setdefault("annotations", {})[CREATE_STARTED_ANNOTATION] = started
    metadata.setdefault("labels", {}).update(labels)
    return True


def create_gate_status(
    api: pykube.HTTPClient,
    capi_cluster,
    selection: AddonSelection,
    now: datetime.datetime | None = None,
) -> GateResult:
    now = now or _now()
    labels = capi_cluster.obj.get("metadata", {}).get("labels", {})
    for wave_number, wave_names in enumerate(selection.waves, start=1):
        wave = tuple(selection.profile(name) for name in wave_names)
        expected_labels = {
            key: value
            for profile in wave
            for key, value in profile.cluster_labels.items()
        }
        if any(labels.get(key) != value for key, value in expected_labels.items()):
            if not _activate_wave(capi_cluster, wave):
                return GateResult(
                    "waiting", "Add-on activation changed concurrently; retrying."
                )
            return GateResult(
                "waiting",
                f"Activated add-on profile wave {wave_number}: {', '.join(wave_names)}.",
            )
        for profile in wave:
            result = _profile_create_status(api, capi_cluster, profile, now)
            if result.state != "ready":
                return GateResult(
                    result.state, f"Add-on profile {profile.name}: {result.reason}"
                )
    return GateResult("ready", "All selected add-on profiles are Ready.")


def _start_delete_wave(
    capi_cluster,
    profiles: tuple[AddonProfile, ...],
    *,
    reset_timeout: bool = False,
) -> bool:
    names = tuple(profile.name for profile in profiles)
    started = _updated_timestamp_map(
        capi_cluster,
        DELETE_STARTED_ANNOTATION,
        names,
        reset=reset_timeout,
    )
    labels = capi_cluster.obj.setdefault("metadata", {}).setdefault("labels", {})
    patch_labels: dict[str, None] = {}
    for profile in profiles:
        for label in profile.cluster_labels:
            if label in labels:
                labels.pop(label)
                patch_labels[label] = None
    if not _patch_lifecycle_metadata(
        capi_cluster,
        annotations={DELETE_STARTED_ANNOTATION: started},
        labels=patch_labels,
    ):
        return False
    capi_cluster.obj.setdefault("metadata", {}).setdefault("annotations", {})[
        DELETE_STARTED_ANNOTATION
    ] = started
    return True


def start_delete(
    capi_cluster,
    selection: AddonSelection,
    *,
    restart_timeout: bool = False,
) -> bool:
    wave = tuple(selection.profile(name) for name in reversed(selection.waves[-1]))
    return _start_delete_wave(capi_cluster, wave, reset_timeout=restart_timeout)


def _profile_delete_status(
    api: pykube.HTTPClient,
    capi_cluster,
    profile: AddonProfile,
    now: datetime.datetime,
) -> GateResult:
    started = _started(capi_cluster, DELETE_STARTED_ANNOTATION, profile.name)
    releases = _get_releases(api, capi_cluster.name, profile.required_helm_chart_proxy)
    if not releases:
        return GateResult("ready", "Required add-on release has been removed.")
    if len(releases) > 1:
        return GateResult(
            "failed", "Multiple HelmReleaseProxy resources block ordered deletion."
        )
    release = releases[0]
    if not _release_identity_matches(release, profile, capi_cluster.name):
        return GateResult(
            "failed", "HelmReleaseProxy identity does not match the add-on profile."
        )

    metadata = release.obj.get("metadata", {})
    if (
        release.obj.get("spec", {}).get("reconcileStrategy")
        == INSTALL_ONCE_RECONCILE_STRATEGY
    ):
        if not metadata.get("deletionTimestamp"):
            release.delete()
        removed_finalizer = _remove_caaph_finalizer(release)
        return GateResult(
            "waiting",
            "Removing the required InstallOnce HelmReleaseProxy"
            f" (CAAPH finalizer removed: {removed_finalizer}).",
        )

    condition = _release_condition(release) or {}
    terminal = _terminal_condition(release, _TERMINAL_DELETE_REASONS)
    reason = (terminal or condition).get("reason", "Deleting")
    message = (terminal or condition).get(
        "message", "Helm release deletion is pending."
    )
    if terminal is not None:
        return GateResult("failed", f"HelmReleaseProxy {reason}: {message}")
    if now - started >= profile.delete_timeout:
        return GateResult(
            "failed", f"Timed out deleting HelmReleaseProxy ({reason}): {message}"
        )
    return GateResult("waiting", f"HelmReleaseProxy {reason}: {message}")


def delete_gate_status(
    api: pykube.HTTPClient,
    capi_cluster,
    selection: AddonSelection,
    now: datetime.datetime | None = None,
) -> GateResult:
    now = now or _now()
    labels = capi_cluster.obj.get("metadata", {}).get("labels", {})
    started = _timestamp_map(capi_cluster, DELETE_STARTED_ANNOTATION)
    for wave_number, wave_names in reversed(tuple(enumerate(selection.waves, start=1))):
        wave = tuple(selection.profile(name) for name in reversed(wave_names))
        wave_active = any(
            label in labels for profile in wave for label in profile.cluster_labels
        )
        wave_started = any(profile.name in started for profile in wave)
        if wave_active and not wave_started:
            if not _start_delete_wave(capi_cluster, wave):
                return GateResult(
                    "waiting", "Add-on deletion changed concurrently; retrying."
                )
            return GateResult(
                "waiting",
                f"Removing add-on profile wave {wave_number}: {', '.join(wave_names)}.",
            )
        if not wave_started:
            continue
        all_ready = True
        for profile in wave:
            result = _profile_delete_status(api, capi_cluster, profile, now)
            if result.state == "failed":
                return GateResult(
                    "failed", f"Add-on profile {profile.name}: {result.reason}"
                )
            if result.state == "waiting":
                all_ready = False
        if not all_ready:
            return GateResult(
                "waiting", f"Waiting for add-on profile wave {wave_number} removal."
            )
        if wave_number > 1:
            next_wave = tuple(
                selection.profile(name)
                for name in reversed(selection.waves[wave_number - 2])
            )
            if not any(profile.name in started for profile in next_wave):
                if not _start_delete_wave(capi_cluster, next_wave):
                    return GateResult(
                        "waiting", "Add-on deletion changed concurrently; retrying."
                    )
                return GateResult(
                    "waiting", f"Removing add-on profile wave {wave_number - 1}."
                )
    return GateResult("ready", "All selected add-on profiles have been removed.")
