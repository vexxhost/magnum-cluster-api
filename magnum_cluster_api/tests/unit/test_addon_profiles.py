# Copyright (c) 2026 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0

import datetime
import hashlib
import json
from unittest import mock

import pytest
from magnum.common import exception  # type: ignore

from magnum_cluster_api import addon_profiles

PROFILE_A = "platform-foundation-v1-deadbeef"
PROFILE_B = "workload-platform-v1-cafebabe"
PROFILE_SET_A = "foundation-stack-v1-a11ce001"
PROFILE_SET_ALL = "platform-stack-v1-feedface"
LABEL_A = f"{addon_profiles.ADDON_LABEL_PREFIX}foundation"
LABEL_B = f"{addon_profiles.ADDON_LABEL_PREFIX}workload"
CAPABILITY = "machine-network.magnum-cluster-api.openstack.org/secondary"


def _profile_yaml(*, schema=True, profile_sets=False):
    prefix = "schemaVersion: 1\n" if schema else ""
    raw = f"""{prefix}profiles:
  {PROFILE_A}:
    category: platform-foundation
    dependsOn: []
    requiresCapabilities: []
    clusterLabels:
      {LABEL_A}: deadbeef
    requiredHelmChartProxy: foundation-v1-deadbeef
    releaseName: foundation
    createTimeout: 45m
    deleteTimeout: 20m
  {PROFILE_B}:
    category: workload-platform
    dependsOn:
      - {PROFILE_A}
    requiresCapabilities:
      - {CAPABILITY}
    clusterLabels:
      {LABEL_B}: cafebabe
    requiredHelmChartProxy: workload-v1-cafebabe
    releaseName: workload
    createTimeout: 90m
    deleteTimeout: 30m
"""
    if profile_sets:
        raw += f"""profileSets:
  {PROFILE_SET_A}:
    profiles:
      - {PROFILE_A}
  {PROFILE_SET_ALL}:
    profiles:
      - {PROFILE_A}
      - {PROFILE_B}
"""
    return raw


def _profile(name, label, hcp, release, *, depends_on=()):
    return addon_profiles.AddonProfile(
        name=name,
        category="generic",
        depends_on=depends_on,
        requires_capabilities=(),
        cluster_labels={label: name[-8:]},
        required_helm_chart_proxy=hcp,
        release_name=release,
        create_timeout=datetime.timedelta(minutes=45),
        delete_timeout=datetime.timedelta(minutes=20),
    )


@pytest.fixture
def profile_a():
    return _profile(PROFILE_A, LABEL_A, "foundation-v1-deadbeef", "foundation")


@pytest.fixture
def profile_b():
    return _profile(
        PROFILE_B,
        LABEL_B,
        "workload-v1-cafebabe",
        "workload",
        depends_on=(PROFILE_A,),
    )


@pytest.fixture
def selection(profile_a, profile_b):
    return addon_profiles._selection(
        (PROFILE_A, PROFILE_B), {PROFILE_A: profile_a, PROFILE_B: profile_b}
    )


@pytest.fixture
def profile_set_selection(profile_a, profile_b):
    catalog = addon_profiles.AddonCatalog(
        profiles={PROFILE_A: profile_a, PROFILE_B: profile_b},
        profile_sets={
            PROFILE_SET_ALL: addon_profiles.AddonProfileSet(
                name=PROFILE_SET_ALL,
                profiles=(PROFILE_A, PROFILE_B),
            )
        },
    )
    return addon_profiles._selection_from_catalog((PROFILE_SET_ALL,), catalog)


@pytest.fixture
def capi_cluster(selection):
    resource = mock.MagicMock()
    resource.name = "capi-cluster"
    _, annotations = addon_profiles.cluster_metadata(selection)
    resource.obj = {
        "metadata": {
            "name": resource.name,
            "resourceVersion": "123",
            "labels": {},
            "annotations": annotations,
        }
    }
    return resource


def _release(
    profile,
    *,
    ready="True",
    reason="Ready",
    generation=2,
    observed_generation=2,
    reconcile_strategy="Continuous",
):
    release = mock.MagicMock()
    release.obj = {
        "metadata": {
            "generation": generation,
            "finalizers": [addon_profiles.HELM_RELEASE_PROXY_FINALIZER],
        },
        "spec": {
            "clusterRef": {"name": "capi-cluster", "namespace": "magnum-system"},
            "releaseName": profile.release_name,
            "reconcileStrategy": reconcile_strategy,
        },
        "status": {
            "observedGeneration": observed_generation,
            "conditions": [
                {
                    "type": "Ready",
                    "status": ready,
                    "reason": reason,
                    "message": "release state",
                    "observedGeneration": observed_generation,
                }
            ],
        },
    }
    return release


def _config_map(mocker, raw):
    config_map = mock.MagicMock()
    config_map.obj = {"data": {addon_profiles.ADDON_PROFILES_CONFIGMAP_KEY: raw}}
    objects = mocker.patch("pykube.ConfigMap.objects").return_value
    objects.get_or_none.return_value = config_map
    return objects


def _mark_create_started(capi_cluster, *profiles):
    value = {profile.name: "2026-08-24T00:00:00Z" for profile in profiles}
    capi_cluster.obj["metadata"]["annotations"][
        addon_profiles.CREATE_STARTED_ANNOTATION
    ] = json.dumps(value, sort_keys=True, separators=(",", ":"))


def _chart_proxy(profile):
    proxy = mock.MagicMock()
    proxy.name = profile.required_helm_chart_proxy
    return proxy


def test_get_profiles_parses_schema_v1_contract(mocker):
    objects = _config_map(mocker, _profile_yaml())

    profiles = addon_profiles.get_profiles(mock.sentinel.api)

    assert tuple(profiles) == (PROFILE_A, PROFILE_B)
    assert profiles[PROFILE_B].depends_on == (PROFILE_A,)
    assert profiles[PROFILE_B].requires_capabilities == (CAPABILITY,)
    objects.get_or_none.assert_called_once_with(
        name=addon_profiles.ADDON_PROFILES_CONFIGMAP
    )


def test_get_catalog_parses_optional_profile_sets(mocker):
    _config_map(mocker, _profile_yaml(profile_sets=True))

    catalog = addon_profiles.get_catalog(mock.sentinel.api)

    assert tuple(catalog.profiles) == (PROFILE_A, PROFILE_B)
    assert catalog.profile_sets[PROFILE_SET_A].profiles == (PROFILE_A,)
    assert catalog.profile_sets[PROFILE_SET_ALL].profiles == (PROFILE_A, PROFILE_B)


@pytest.mark.parametrize(
    "raw",
    [
        _profile_yaml(schema=False),
        _profile_yaml().replace("schemaVersion: 1", "schemaVersion: 2"),
        _profile_yaml().replace("    createTimeout: 45m", "    unsupported: true"),
        _profile_yaml().replace("    createTimeout: 45m", "    createTimeout: 25h"),
    ],
)
def test_get_profiles_rejects_invalid_contract(mocker, raw):
    _config_map(mocker, raw)

    with pytest.raises(exception.Invalid):
        addon_profiles.get_profiles(mock.sentinel.api)


def test_get_profiles_rejects_colliding_labels(mocker):
    raw = _profile_yaml().replace(LABEL_B, LABEL_A)
    _config_map(mocker, raw)

    with pytest.raises(exception.Invalid, match="owned by both"):
        addon_profiles.get_profiles(mock.sentinel.api)


def test_get_profiles_rejects_dependency_cycle(mocker):
    raw = _profile_yaml().replace("    dependsOn: []", f"    dependsOn: [{PROFILE_B}]")
    _config_map(mocker, raw)

    with pytest.raises(exception.Invalid, match="cycle"):
        addon_profiles.get_profiles(mock.sentinel.api)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            _profile_yaml(profile_sets=True).replace(
                f"      - {PROFILE_B}\n", "      - missing-profile-v1-deadbeef\n"
            ),
            "missing profile",
        ),
        (
            _profile_yaml(profile_sets=True).replace(
                f"  {PROFILE_SET_A}:\n", f"  {PROFILE_A}:\n"
            ),
            "both a profile and a profile set",
        ),
        (
            _profile_yaml(profile_sets=True).replace(
                f"  {PROFILE_SET_A}:\n    profiles:\n      - {PROFILE_A}\n",
                f"  {PROFILE_SET_A}:\n    profiles: []\n",
            ),
            "must not be empty",
        ),
        (
            _profile_yaml(profile_sets=True).replace(
                f"  {PROFILE_SET_A}:\n    profiles:\n",
                f"  {PROFILE_SET_A}:\n    unsupported: true\n    profiles:\n",
            ),
            "unsupported field",
        ),
        (
            _profile_yaml(profile_sets=True).replace(
                f"      - {PROFILE_A}\n  {PROFILE_SET_ALL}:\n",
                f"      - {PROFILE_B}\n  {PROFILE_SET_ALL}:\n",
            ),
            "unselected dependency",
        ),
    ],
)
def test_get_catalog_rejects_invalid_profile_sets(mocker, raw, message):
    _config_map(mocker, raw)

    with pytest.raises(exception.Invalid, match=message):
        addon_profiles.get_catalog(mock.sentinel.api)


@pytest.mark.parametrize(
    "labels",
    [
        {"kube_tag": "v1.28.0", "os_distro": "ubuntu"},
        {"kube_tag": "v1.34.8", "os_distro": "ubuntu"},
    ],
)
def test_prepare_cluster_without_profile_is_a_noop(mocker, labels):
    cluster = mock.MagicMock()
    cluster.labels = dict(labels)
    cluster.cluster_template.labels = dict(labels)
    config_maps = mocker.patch("pykube.ConfigMap.objects")

    assert addon_profiles.prepare_cluster(mock.sentinel.api, cluster) is None
    config_maps.assert_not_called()
    assert cluster.labels == labels


def test_prepare_cluster_rejects_old_singular_spelling(mocker):
    cluster = mock.MagicMock()
    cluster.labels = {}
    cluster.cluster_template.labels = {"addon_profile": PROFILE_A}
    config_maps = mocker.patch("pykube.ConfigMap.objects")

    with pytest.raises(exception.Invalid, match="Unsupported label"):
        addon_profiles.prepare_cluster(mock.sentinel.api, cluster)
    config_maps.assert_not_called()


def test_prepare_cluster_rejects_create_override():
    cluster = mock.MagicMock()
    cluster.labels = {addon_profiles.ADDON_PROFILES_LABEL: PROFILE_A}
    cluster.cluster_template.labels = {
        addon_profiles.ADDON_PROFILES_LABEL: f"{PROFILE_A}+{PROFILE_B}"
    }

    with pytest.raises(exception.Invalid, match="cannot be overridden"):
        addon_profiles.prepare_cluster(mock.sentinel.api, cluster)


def test_prepare_cluster_inherits_ordered_selection(mocker, profile_a, profile_b):
    cluster = mock.MagicMock()
    cluster.labels = {}
    selected = f"{PROFILE_A}+{PROFILE_B}"
    cluster.cluster_template.labels = {addon_profiles.ADDON_PROFILES_LABEL: selected}
    mocker.patch.object(
        addon_profiles,
        "get_catalog",
        return_value=addon_profiles.AddonCatalog(
            profiles={PROFILE_A: profile_a, PROFILE_B: profile_b},
            profile_sets={},
        ),
    )

    resolved = addon_profiles.prepare_cluster(mock.sentinel.api, cluster)

    assert resolved.names == (PROFILE_A, PROFILE_B)
    assert resolved.waves == ((PROFILE_A,), (PROFILE_B,))
    assert cluster.labels[addon_profiles.ADDON_PROFILES_LABEL] == selected


def test_prepare_cluster_expands_profile_set(mocker, profile_a, profile_b):
    cluster = mock.MagicMock()
    cluster.labels = {}
    cluster.cluster_template.labels = {
        addon_profiles.ADDON_PROFILES_LABEL: PROFILE_SET_ALL
    }
    mocker.patch.object(
        addon_profiles,
        "get_catalog",
        return_value=addon_profiles.AddonCatalog(
            profiles={PROFILE_A: profile_a, PROFILE_B: profile_b},
            profile_sets={
                PROFILE_SET_ALL: addon_profiles.AddonProfileSet(
                    name=PROFILE_SET_ALL,
                    profiles=(PROFILE_A, PROFILE_B),
                )
            },
        ),
    )

    resolved = addon_profiles.prepare_cluster(mock.sentinel.api, cluster)

    assert resolved.names == (PROFILE_A, PROFILE_B)
    assert resolved.requested_selectors == (PROFILE_SET_ALL,)
    assert tuple(profile_set.name for profile_set in resolved.profile_sets) == (
        PROFILE_SET_ALL,
    )
    assert cluster.labels[addon_profiles.ADDON_PROFILES_LABEL] == PROFILE_SET_ALL


def test_mixed_profile_and_profile_set_selection(profile_a, profile_b):
    catalog = addon_profiles.AddonCatalog(
        profiles={PROFILE_A: profile_a, PROFILE_B: profile_b},
        profile_sets={
            PROFILE_SET_A: addon_profiles.AddonProfileSet(
                name=PROFILE_SET_A,
                profiles=(PROFILE_A,),
            )
        },
    )

    selection = addon_profiles._selection_from_catalog(
        (PROFILE_SET_A, PROFILE_B), catalog
    )

    assert selection.names == (PROFILE_A, PROFILE_B)
    assert selection.requested_selectors == (PROFILE_SET_A, PROFILE_B)


def test_overlapping_selectors_are_rejected(profile_a, profile_b):
    catalog = addon_profiles.AddonCatalog(
        profiles={PROFILE_A: profile_a, PROFILE_B: profile_b},
        profile_sets={
            PROFILE_SET_ALL: addon_profiles.AddonProfileSet(
                name=PROFILE_SET_ALL,
                profiles=(PROFILE_A, PROFILE_B),
            )
        },
    )

    with pytest.raises(exception.Invalid, match="selected by both"):
        addon_profiles._selection_from_catalog((PROFILE_SET_ALL, PROFILE_A), catalog)


def test_selection_requires_dependencies_to_be_explicit(profile_a, profile_b):
    with pytest.raises(exception.Invalid, match="unselected dependency"):
        addon_profiles._selection(
            (PROFILE_B,), {PROFILE_A: profile_a, PROFILE_B: profile_b}
        )


def test_snapshot_is_canonical_and_round_trips(selection, capi_cluster):
    assert len(selection.digest) == 64
    assert selection.digest == (
        "ec8713a369a08ae663f5b45fcef264b9f7744bf66ef6168837f7799e2aa6b812"
    )
    assert (
        json.dumps(
            json.loads(selection.contract), sort_keys=True, separators=(",", ":")
        )
        == selection.contract
    )

    restored = addon_profiles.selection_from_cluster(capi_cluster)

    assert restored == selection
    assert set(json.loads(selection.contract)) == {
        "profiles",
        "schemaVersion",
        "selectedProfiles",
        "waves",
    }


def test_profile_set_snapshot_is_canonical_and_round_trips(profile_set_selection):
    capi_cluster = mock.MagicMock()
    _, annotations = addon_profiles.cluster_metadata(profile_set_selection)
    capi_cluster.obj = {"metadata": {"annotations": annotations}}

    document = json.loads(profile_set_selection.contract)
    restored = addon_profiles.selection_from_cluster(capi_cluster)

    assert restored == profile_set_selection
    assert document["schemaVersion"] == 1
    assert document["requestedSelectors"] == [PROFILE_SET_ALL]
    assert document["selectedProfileSets"] == {PROFILE_SET_ALL: [PROFILE_A, PROFILE_B]}
    assert annotations[addon_profiles.SELECTED_PROFILES_ANNOTATION] == (
        f"{PROFILE_A}+{PROFILE_B}"
    )


def test_profile_set_snapshot_rejects_expansion_mismatch(profile_set_selection):
    capi_cluster = mock.MagicMock()
    _, annotations = addon_profiles.cluster_metadata(profile_set_selection)
    document = json.loads(profile_set_selection.contract)
    document["selectedProfileSets"][PROFILE_SET_ALL] = [PROFILE_A]
    contract = json.dumps(document, sort_keys=True, separators=(",", ":"))
    annotations[addon_profiles.PROFILES_CONTRACT_ANNOTATION] = contract
    annotations[addon_profiles.PROFILES_CONTRACT_SHA256_ANNOTATION] = hashlib.sha256(
        contract.encode("utf-8")
    ).hexdigest()
    capi_cluster.obj = {"metadata": {"annotations": annotations}}

    with pytest.raises(exception.Invalid, match="do not match selectedProfiles"):
        addon_profiles.selection_from_cluster(capi_cluster)


def test_snapshot_rejects_digest_mismatch(capi_cluster):
    capi_cluster.obj["metadata"]["annotations"][
        addon_profiles.PROFILES_CONTRACT_SHA256_ANNOTATION
    ] = ("0" * 64)

    with pytest.raises(exception.Invalid, match="digest"):
        addon_profiles.selection_from_cluster(capi_cluster)


def test_snapshot_rejects_invalid_selected_profiles(selection, capi_cluster):
    document = json.loads(selection.contract)
    document["selectedProfiles"] = PROFILE_A
    contract = json.dumps(document, sort_keys=True, separators=(",", ":"))
    annotations = capi_cluster.obj["metadata"]["annotations"]
    annotations[addon_profiles.PROFILES_CONTRACT_ANNOTATION] = contract
    annotations[addon_profiles.PROFILES_CONTRACT_SHA256_ANNOTATION] = hashlib.sha256(
        contract.encode("utf-8")
    ).hexdigest()

    with pytest.raises(exception.Invalid, match="selectedProfiles"):
        addon_profiles.selection_from_cluster(capi_cluster)


def test_cluster_metadata_does_not_activate_profiles(selection):
    labels, annotations = addon_profiles.cluster_metadata(selection)

    assert labels == {}
    assert annotations[addon_profiles.SELECTED_PROFILES_ANNOTATION] == (
        f"{PROFILE_A}+{PROFILE_B}"
    )
    assert (
        annotations[addon_profiles.PROFILES_CONTRACT_ANNOTATION] == selection.contract
    )


def test_migrate_legacy_selection_snapshots_existing_cluster(mocker, profile_a):
    capi_cluster = mock.MagicMock()
    capi_cluster.obj = {
        "metadata": {
            "resourceVersion": "123",
            "labels": dict(profile_a.cluster_labels),
            "annotations": {
                addon_profiles.LEGACY_PROFILE_ANNOTATION: PROFILE_A,
                addon_profiles.LEGACY_HELM_CHART_PROXY_ANNOTATION: (
                    profile_a.required_helm_chart_proxy
                ),
                addon_profiles.LEGACY_RELEASE_NAME_ANNOTATION: (profile_a.release_name),
            },
        }
    }
    mocker.patch.object(
        addon_profiles,
        "get_profiles",
        return_value={PROFILE_A: profile_a},
    )

    selection = addon_profiles.migrate_legacy_selection(
        mock.sentinel.api,
        capi_cluster,
        PROFILE_A,
    )

    assert selection is not None
    assert selection.names == (PROFILE_A,)
    annotations = capi_cluster.obj["metadata"]["annotations"]
    assert annotations[addon_profiles.SELECTED_PROFILES_ANNOTATION] == PROFILE_A
    capi_cluster.patch.assert_called_once()


def test_migrate_legacy_selection_rejects_identity_mismatch(mocker, profile_a):
    capi_cluster = mock.MagicMock()
    capi_cluster.obj = {
        "metadata": {
            "labels": dict(profile_a.cluster_labels),
            "annotations": {
                addon_profiles.LEGACY_PROFILE_ANNOTATION: PROFILE_A,
                addon_profiles.LEGACY_HELM_CHART_PROXY_ANNOTATION: "other-proxy",
                addon_profiles.LEGACY_RELEASE_NAME_ANNOTATION: profile_a.release_name,
            },
        }
    }
    mocker.patch.object(
        addon_profiles,
        "get_profiles",
        return_value={PROFILE_A: profile_a},
    )

    with pytest.raises(exception.Invalid, match="HelmChartProxy"):
        addon_profiles.migrate_legacy_selection(
            mock.sentinel.api,
            capi_cluster,
            PROFILE_A,
        )


def test_create_gate_activates_only_first_wave(selection, capi_cluster):
    result = addon_profiles.create_gate_status(
        mock.sentinel.api,
        capi_cluster,
        selection,
        now=datetime.datetime(2026, 8, 24, 0, 1, tzinfo=datetime.timezone.utc),
    )

    assert result.state == "waiting"
    assert PROFILE_A in result.reason
    assert capi_cluster.obj["metadata"]["labels"] == {
        LABEL_A: selection.profile(PROFILE_A).cluster_labels[LABEL_A]
    }
    assert LABEL_B not in capi_cluster.obj["metadata"]["labels"]
    patch = capi_cluster.patch.call_args.args[0]["metadata"]
    assert patch["labels"] == {
        LABEL_A: selection.profile(PROFILE_A).cluster_labels[LABEL_A]
    }
    assert PROFILE_A in json.loads(
        patch["annotations"][addon_profiles.CREATE_STARTED_ANNOTATION]
    )
    assert patch["resourceVersion"] == "123"


def test_create_gate_retries_metadata_conflict(selection, capi_cluster):
    capi_cluster.patch.side_effect = addon_profiles.pykube.exceptions.HTTPError(
        409, "conflict"
    )

    result = addon_profiles.create_gate_status(
        mock.sentinel.api, capi_cluster, selection
    )

    assert result.state == "waiting"
    assert "concurrently" in result.reason
    capi_cluster.reload.assert_called_once_with()
    assert capi_cluster.obj["metadata"]["labels"] == {}


def test_create_gate_activates_second_wave_after_first_ready(
    mocker, selection, capi_cluster
):
    profile_a = selection.profile(PROFILE_A)
    capi_cluster.obj["metadata"]["labels"].update(profile_a.cluster_labels)
    _mark_create_started(capi_cluster, profile_a)
    mocker.patch.object(
        addon_profiles, "_profile_chart_proxies", return_value=[_chart_proxy(profile_a)]
    )
    mocker.patch.object(
        addon_profiles, "_get_releases", return_value=[_release(profile_a)]
    )

    result = addon_profiles.create_gate_status(
        mock.sentinel.api, capi_cluster, selection
    )

    assert result.state == "waiting"
    assert "wave 2" in result.reason
    assert LABEL_B in capi_cluster.obj["metadata"]["labels"]


def test_create_gate_requires_current_ready_status(mocker, profile_a):
    selection = addon_profiles._selection((PROFILE_A,), {PROFILE_A: profile_a})
    capi_cluster = mock.MagicMock()
    capi_cluster.name = "capi-cluster"
    _, annotations = addon_profiles.cluster_metadata(selection)
    capi_cluster.obj = {
        "metadata": {
            "labels": dict(profile_a.cluster_labels),
            "annotations": annotations,
        }
    }
    _mark_create_started(capi_cluster, profile_a)
    mocker.patch.object(
        addon_profiles, "_profile_chart_proxies", return_value=[_chart_proxy(profile_a)]
    )
    mocker.patch.object(
        addon_profiles,
        "_get_releases",
        return_value=[_release(profile_a, observed_generation=1)],
    )

    result = addon_profiles.create_gate_status(
        mock.sentinel.api,
        capi_cluster,
        selection,
        now=datetime.datetime(2026, 8, 24, 0, 1, tzinfo=datetime.timezone.utc),
    )

    assert result.state == "waiting"
    assert "current" in result.reason


def test_create_gate_reports_all_profiles_ready(mocker, selection, capi_cluster):
    for profile in selection.profiles:
        capi_cluster.obj["metadata"]["labels"].update(profile.cluster_labels)
    _mark_create_started(capi_cluster, *selection.profiles)
    mocker.patch.object(
        addon_profiles,
        "_profile_chart_proxies",
        side_effect=lambda api, cluster, profile: [_chart_proxy(profile)],
    )
    mocker.patch.object(
        addon_profiles,
        "_get_releases",
        side_effect=lambda api, cluster, hcp: [
            _release(
                next(
                    profile
                    for profile in selection.profiles
                    if profile.required_helm_chart_proxy == hcp
                )
            )
        ],
    )

    result = addon_profiles.create_gate_status(
        mock.sentinel.api, capi_cluster, selection
    )

    assert result == addon_profiles.GateResult(
        "ready", "All selected add-on profiles are Ready."
    )


def test_delete_starts_with_last_dependency_wave(selection, capi_cluster):
    for profile in selection.profiles:
        capi_cluster.obj["metadata"]["labels"].update(profile.cluster_labels)

    addon_profiles.start_delete(capi_cluster, selection)

    assert LABEL_A in capi_cluster.obj["metadata"]["labels"]
    assert LABEL_B not in capi_cluster.obj["metadata"]["labels"]
    started = json.loads(
        capi_cluster.obj["metadata"]["annotations"][
            addon_profiles.DELETE_STARTED_ANNOTATION
        ]
    )
    assert set(started) == {PROFILE_B}
    patch = capi_cluster.patch.call_args.args[0]["metadata"]
    assert patch["labels"] == {LABEL_B: None}
    assert set(
        json.loads(patch["annotations"][addon_profiles.DELETE_STARTED_ANNOTATION])
    ) == {PROFILE_B}
    assert patch["resourceVersion"] == "123"


def test_delete_advances_in_reverse_wave_order(mocker, selection, capi_cluster):
    for profile in selection.profiles:
        capi_cluster.obj["metadata"]["labels"].update(profile.cluster_labels)
    addon_profiles.start_delete(capi_cluster, selection)
    mocker.patch.object(addon_profiles, "_get_releases", return_value=[])

    result = addon_profiles.delete_gate_status(
        mock.sentinel.api, capi_cluster, selection
    )

    assert result.state == "waiting"
    assert "wave 1" in result.reason
    assert LABEL_A not in capi_cluster.obj["metadata"]["labels"]
    result = addon_profiles.delete_gate_status(
        mock.sentinel.api, capi_cluster, selection
    )
    assert result.state == "ready"


def test_delete_install_once_removes_only_caaph_finalizer(mocker, profile_a):
    selection = addon_profiles._selection((PROFILE_A,), {PROFILE_A: profile_a})
    capi_cluster = mock.MagicMock()
    capi_cluster.name = "capi-cluster"
    _, annotations = addon_profiles.cluster_metadata(selection)
    capi_cluster.obj = {
        "metadata": {
            "labels": dict(profile_a.cluster_labels),
            "annotations": annotations,
        }
    }
    addon_profiles.start_delete(capi_cluster, selection)
    release = _release(profile_a, reconcile_strategy="InstallOnce")
    release.obj["metadata"]["finalizers"].append("example.org/retained")
    mocker.patch.object(addon_profiles, "_get_releases", return_value=[release])

    result = addon_profiles.delete_gate_status(
        mock.sentinel.api, capi_cluster, selection
    )

    assert result.state == "waiting"
    release.delete.assert_called_once_with()
    release.patch.assert_called_once_with(
        {"metadata": {"finalizers": ["example.org/retained"]}}
    )
