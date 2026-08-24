# Copyright (c) 2026 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0

import types

from magnum_cluster_api import profile_contracts


def test_no_profiles_have_no_bundle_annotation():
    assert profile_contracts.cluster_metadata(None, None) == {}


def test_profile_bundle_is_deterministic_and_covers_both_contracts():
    addons = types.SimpleNamespace(names=("platform", "serving"), digest="a" * 64)
    machine_network = types.SimpleNamespace(name="secondary-network", digest="b" * 64)

    first = profile_contracts.cluster_metadata(addons, machine_network)
    second = profile_contracts.cluster_metadata(addons, machine_network)

    assert first == second
    assert len(first[profile_contracts.BUNDLE_SHA256_ANNOTATION]) == 64


def test_changing_one_contract_changes_bundle_digest():
    addons = types.SimpleNamespace(names=("platform",), digest="a" * 64)
    machine_network = types.SimpleNamespace(name="secondary-network", digest="b" * 64)
    changed = types.SimpleNamespace(name="secondary-network", digest="c" * 64)

    assert profile_contracts.cluster_metadata(
        addons, machine_network
    ) != profile_contracts.cluster_metadata(addons, changed)
