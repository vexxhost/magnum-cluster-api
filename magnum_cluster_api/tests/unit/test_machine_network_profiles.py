# Copyright (c) 2026 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0

import dataclasses
import hashlib
import json
from unittest import mock

import pytest
import yaml
from magnum.common import exception  # type: ignore

from magnum_cluster_api import machine_network_profiles

PROFILE = "secondary-network-v1-deadbeef"
NETWORK_A = "11111111-1111-4111-8111-111111111111"
NETWORK_B = "22222222-2222-4222-8222-222222222222"
SUBNET_A = "33333333-3333-4333-8333-333333333333"
SUBNET_B = "44444444-4444-4444-8444-444444444444"
CAPABILITY = "machine-network.magnum-cluster-api.openstack.org/secondary"


def _profile_yaml(*, applies_to="all", capabilities=(CAPABILITY,), schema=True):
    prefix = "schemaVersion: 1\n" if schema else ""
    capability_lines = " []"
    if capabilities:
        capability_lines = "\n" + "\n".join(
            f"      - {capability}" for capability in capabilities
        )
    return f"""{prefix}profiles:
  {PROFILE}:
    mode: augment
    appliesTo: {applies_to}
    providesCapabilities:{capability_lines}
    additionalPorts:
      - role: data
        networkID: {NETWORK_B}
        fixedIPs:
          - subnetID: {SUBNET_B}
        vnicType: normal
        portSecurityEnabled: false
"""


def _config_map(mocker, raw):
    config_map = mock.MagicMock()
    config_map.obj = {
        "data": {machine_network_profiles.MACHINE_NETWORK_PROFILES_CONFIGMAP_KEY: raw}
    }
    objects = mocker.patch("pykube.ConfigMap.objects").return_value
    objects.get_or_none.return_value = config_map
    return objects


def _cluster(*, template_profile=None, cluster_profile=None, nodegroups=()):
    cluster = mock.MagicMock()
    cluster.cluster_template.labels = {}
    if template_profile is not None:
        cluster.cluster_template.labels[
            machine_network_profiles.MACHINE_NETWORK_PROFILE_LABEL
        ] = template_profile
    cluster.labels = {}
    if cluster_profile is not None:
        cluster.labels[machine_network_profiles.MACHINE_NETWORK_PROFILE_LABEL] = (
            cluster_profile
        )
    cluster.nodegroups = list(nodegroups)
    return cluster


def _selection(*, applies_to="all", capabilities=(CAPABILITY,)):
    document = _profile_yaml(applies_to=applies_to, capabilities=capabilities)
    profile = json.loads(json.dumps(yaml.safe_load(document)))["profiles"][PROFILE]
    return machine_network_profiles._selection(PROFILE, profile)


def test_no_selector_does_not_read_config_map(mocker):
    objects = mocker.patch("pykube.ConfigMap.objects")

    result = machine_network_profiles.prepare_cluster(mock.sentinel.api, _cluster())

    assert result is None
    objects.assert_not_called()


def test_cluster_request_cannot_add_profile(mocker):
    objects = mocker.patch("pykube.ConfigMap.objects")

    with pytest.raises(exception.Invalid, match="cannot be overridden"):
        machine_network_profiles.prepare_cluster(
            mock.sentinel.api, _cluster(cluster_profile=PROFILE)
        )

    objects.assert_not_called()


def test_profile_is_inherited_and_normalized(mocker):
    _config_map(mocker, _profile_yaml())
    cluster = _cluster(template_profile=PROFILE)

    selection = machine_network_profiles.prepare_cluster(mock.sentinel.api, cluster)

    assert selection.name == PROFILE
    assert selection.provides_capabilities == (CAPABILITY,)
    assert (
        cluster.labels[machine_network_profiles.MACHINE_NETWORK_PROFILE_LABEL]
        == PROFILE
    )


def test_versionless_document_is_rejected(mocker):
    _config_map(mocker, _profile_yaml(schema=False))

    with pytest.raises(exception.Invalid, match="schemaVersion"):
        machine_network_profiles.get_profiles(mock.sentinel.api)


def test_unknown_port_field_is_rejected(mocker):
    raw = _profile_yaml().replace(
        "        vnicType: normal",
        "        vnicType: normal\n        unsupported: true",
    )
    _config_map(mocker, raw)

    with pytest.raises(exception.Invalid, match="unsupported field"):
        machine_network_profiles.get_profiles(mock.sentinel.api)


def test_reserved_primary_role_is_rejected(mocker):
    _config_map(mocker, _profile_yaml().replace("role: data", "role: primary"))

    with pytest.raises(exception.Invalid, match="reserved"):
        machine_network_profiles.get_profiles(mock.sentinel.api)


def test_snapshot_round_trip_and_digest():
    selection = _selection()
    annotations = machine_network_profiles.cluster_metadata(selection)
    capi_cluster = mock.MagicMock()
    capi_cluster.obj = {"metadata": {"annotations": annotations}}

    restored = machine_network_profiles.selection_from_cluster(capi_cluster)

    assert restored == selection
    assert (
        selection.digest
        == hashlib.sha256(selection.contract.encode("utf-8")).hexdigest()
    )


def test_snapshot_round_trip_with_omitted_optional_port_fields():
    profile = yaml.safe_load(_profile_yaml())["profiles"][PROFILE]
    port = profile["additionalPorts"][0]
    port.pop("fixedIPs")
    port.pop("vnicType")
    port.pop("portSecurityEnabled")
    selection = machine_network_profiles._selection(PROFILE, profile)
    capi_cluster = mock.MagicMock()
    capi_cluster.obj = {
        "metadata": {
            "annotations": machine_network_profiles.cluster_metadata(selection)
        }
    }

    assert machine_network_profiles.selection_from_cluster(capi_cluster) == selection


def test_snapshot_rejects_tampering():
    selection = _selection()
    annotations = machine_network_profiles.cluster_metadata(selection)
    annotations[machine_network_profiles.CONTRACT_ANNOTATION] += " "
    capi_cluster = mock.MagicMock()
    capi_cluster.obj = {"metadata": {"annotations": annotations}}

    with pytest.raises(exception.Invalid, match="digest"):
        machine_network_profiles.selection_from_cluster(capi_cluster)


def test_render_machine_ports_preserves_primary_and_adds_secondary():
    ports = machine_network_profiles.render_machine_ports(
        _selection(), NETWORK_A, SUBNET_A
    )

    assert ports == [
        {
            "nameSuffix": "primary",
            "network": {"id": NETWORK_A},
            "fixedIPs": [{"subnet": {"id": SUBNET_A}}],
        },
        {
            "nameSuffix": "data",
            "network": {"id": NETWORK_B},
            "fixedIPs": [{"subnet": {"id": SUBNET_B}}],
            "vnicType": "normal",
            "disablePortSecurity": True,
        },
    ]


def test_render_requires_existing_fixed_primary_network():
    with pytest.raises(exception.Invalid, match="existing fixed"):
        machine_network_profiles.render_machine_ports(_selection(), "", None)


def test_render_rejects_duplicate_primary_network_and_subnet():
    selection = _selection()
    port = selection.additional_ports[0]
    duplicate = machine_network_profiles.AdditionalPort(
        role=port.role,
        network_id=NETWORK_A,
        fixed_ips=(machine_network_profiles.FixedIP(SUBNET_A),),
        vnic_type=port.vnic_type,
        port_security_enabled=port.port_security_enabled,
    )
    selection = dataclasses.replace(selection, additional_ports=(duplicate,))

    with pytest.raises(exception.Invalid, match="duplicates the primary"):
        machine_network_profiles.render_machine_ports(selection, NETWORK_A, SUBNET_A)


def test_named_nodegroup_target_is_rejected_in_v1(mocker):
    _config_map(mocker, _profile_yaml(applies_to="nodegroup:workers-b"))

    with pytest.raises(
        exception.Invalid, match="expected all, control-plane, or workers"
    ):
        machine_network_profiles.get_profiles(mock.sentinel.api)


def test_scoped_profile_cannot_provide_cluster_capabilities(mocker):
    _config_map(mocker, _profile_yaml(applies_to="workers"))

    with pytest.raises(exception.Invalid, match="appliesTo must be all"):
        machine_network_profiles.get_profiles(mock.sentinel.api)


def test_scoped_profile_without_capabilities_is_supported(mocker):
    _config_map(
        mocker,
        _profile_yaml(applies_to="workers", capabilities=()),
    )

    profiles = machine_network_profiles.get_profiles(mock.sentinel.api)
    selection = machine_network_profiles._selection(PROFILE, profiles[PROFILE])

    assert selection.applies_to == "workers"
    assert selection.provides_capabilities == ()
