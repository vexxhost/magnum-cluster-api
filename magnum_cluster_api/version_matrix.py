# Copyright (c) 2024 VEXXHOST, Inc.
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

"""
Version compatibility matrix for magnum-cluster-api.

This module defines which Kubernetes versions are supported or deprecated
for the current version of magnum-cluster-api.

The deprecated versions list serves two purposes:
1. Warn users about versions that will become unsupported in future mcapi versions
2. Help operators identify clusters that may fail after an mcapi version upgrade
"""

from __future__ import annotations

from typing import List

import semver


class VersionStatus:
    """Status of a Kubernetes version."""

    SUPPORTED = "supported"
    DEPRECATED = "deprecated"
    UNSUPPORTED = "unsupported"


# Supported Kubernetes versions for the current magnum-cluster-api version
# These are the versions that are fully supported and tested
SUPPORTED_KUBERNETES_VERSIONS: List[str] = [
    "v1.27.3",
    "v1.27.8",
    "v1.27.15",
    "v1.28.11",
    "v1.29.6",
    "v1.30.2",
    "v1.31.1",
]

# Deprecated Kubernetes versions for the current magnum-cluster-api version
# These versions are still supported but will be removed in a future mcapi version
# Operators should use this list to identify clusters that need upgrading
DEPRECATED_KUBERNETES_VERSIONS: List[str] = [
    "v1.26.2",
    "v1.26.6",
    "v1.26.11",
    "v1.25.3",
    "v1.25.11",
]


def parse_k8s_version(version: str) -> semver.VersionInfo | None:
    """
    Parse Kubernetes version string to semver.VersionInfo.

    :param version: Kubernetes version string (e.g., "v1.27.3")
    :return: semver.VersionInfo or None if parsing fails
    """
    # Remove 'v' prefix if present
    version_str = version.lstrip("vV")
    try:
        return semver.VersionInfo.parse(version_str)
    except (ValueError, TypeError):
        return None


def get_version_status(k8s_version: str) -> tuple[str, str | None]:
    """
    Get the status of a Kubernetes version for the current mcapi version.

    :param k8s_version: Kubernetes version (e.g., "v1.27.3")
    :return: Tuple of (status, message) where status is one of:
             VersionStatus.SUPPORTED, VersionStatus.DEPRECATED, VersionStatus.UNSUPPORTED
             and message is an optional human-readable message
    """
    supported = set(SUPPORTED_KUBERNETES_VERSIONS)
    deprecated = set(DEPRECATED_KUBERNETES_VERSIONS)

    # Normalize k8s version for comparison (handle patch version variations)
    k8s_parsed = parse_k8s_version(k8s_version)
    if k8s_parsed is None:
        return (
            VersionStatus.UNSUPPORTED,
            f"Invalid Kubernetes version format: {k8s_version}",
        )

    # Check if exact version matches
    if k8s_version in supported:
        return VersionStatus.SUPPORTED, None

    if k8s_version in deprecated:
        return (
            VersionStatus.DEPRECATED,
            f"Kubernetes version {k8s_version} is deprecated. "
            "Please upgrade to a supported version before upgrading magnum-cluster-api.",
        )

    # Check if same minor version is supported (e.g., v1.27.3 is supported, v1.27.5 might work)
    k8s_minor = f"v{k8s_parsed.major}.{k8s_parsed.minor}"
    supported_minors = {
        f"v{parse_k8s_version(v).major}.{parse_k8s_version(v).minor}"
        for v in supported
        if parse_k8s_version(v) is not None
    }
    deprecated_minors = {
        f"v{parse_k8s_version(v).major}.{parse_k8s_version(v).minor}"
        for v in deprecated
        if parse_k8s_version(v) is not None
    }

    if k8s_minor in supported_minors:
        return (
            VersionStatus.SUPPORTED,
            f"Kubernetes version {k8s_version} (minor {k8s_minor}) is supported, "
            "though specific patch version may not be tested.",
        )

    if k8s_minor in deprecated_minors:
        return (
            VersionStatus.DEPRECATED,
            f"Kubernetes version {k8s_version} (minor {k8s_minor}) is deprecated. "
            "Please upgrade to a supported version before upgrading magnum-cluster-api.",
        )

    # Check if version is too old or too new
    all_versions = list(supported) + list(deprecated)
    if not all_versions:
        return VersionStatus.UNSUPPORTED, "No version information available"

    parsed_versions = [
        parse_k8s_version(v) for v in all_versions if parse_k8s_version(v) is not None
    ]
    if not parsed_versions:
        return VersionStatus.UNSUPPORTED, "Could not parse version information"

    min_version = min(parsed_versions)
    max_version = max(parsed_versions)

    if k8s_parsed < min_version:
        return (
            VersionStatus.UNSUPPORTED,
            f"Kubernetes version {k8s_version} is too old. "
            f"Minimum supported version is {min_version}.",
        )

    if k8s_parsed > max_version:
        return (
            VersionStatus.UNSUPPORTED,
            f"Kubernetes version {k8s_version} is too new. "
            f"Maximum supported version is {max_version}.",
        )

    return (
        VersionStatus.UNSUPPORTED,
        f"Kubernetes version {k8s_version} is not supported.",
    )


def get_supported_versions() -> List[str]:
    """
    Get list of supported Kubernetes versions for the current mcapi version.

    :return: List of supported Kubernetes versions
    """
    return SUPPORTED_KUBERNETES_VERSIONS.copy()


def get_deprecated_versions() -> List[str]:
    """
    Get list of deprecated Kubernetes versions for the current mcapi version.

    This list helps operators identify clusters that may fail after an mcapi upgrade.

    :return: List of deprecated Kubernetes versions
    """
    return DEPRECATED_KUBERNETES_VERSIONS.copy()
