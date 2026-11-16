# Copyright (c) 2026 VEXXHOST, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0

import hashlib
import json

from magnum_cluster_api import addon_profiles, machine_network_profiles

CONTRACTS_ANNOTATION_PREFIX = "contracts.magnum-cluster-api.openstack.org/"
BUNDLE_SHA256_ANNOTATION = f"{CONTRACTS_ANNOTATION_PREFIX}bundle-sha256"


def cluster_metadata(
    addon_selection: addon_profiles.AddonSelection | None,
    machine_network_selection: machine_network_profiles.MachineNetworkSelection | None,
) -> dict[str, str]:
    components: list[dict] = []
    if machine_network_selection is not None:
        components.append(
            {
                "kind": "machine-network",
                "name": machine_network_selection.name,
                "sha256": machine_network_selection.digest,
            }
        )
    if addon_selection is not None:
        components.append(
            {
                "kind": "addons",
                "names": list(addon_selection.names),
                "sha256": addon_selection.digest,
            }
        )
    if not components:
        return {}
    canonical = json.dumps(
        {"components": components, "schemaVersion": 1},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return {
        BUNDLE_SHA256_ANNOTATION: hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    }
