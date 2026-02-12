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
for the current version of magnum-cluster-api using version constraints.

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


# Supported Kubernetes version range for the current magnum-cluster-api version
# These define the minimum and maximum versions that are fully supported and tested
# Format: Version strings (e.g., "v1.27.0", "v1.31.0")
# Versions >= MIN_SUPPORTED and <= MAX_SUPPORTED are supported
MIN_SUPPORTED_KUBERNETES_VERSION: str = "v1.32.0"
MAX_SUPPORTED_KUBERNETES_VERSION: str = "v1.34.2"

# Deprecated Kubernetes version range for the current magnum-cluster-api version
# These versions are still supported but will be removed in a future mcapi version
# Operators should use this to identify clusters that need upgrading
# Format: Version strings (e.g., "v1.25.0", "v1.26.99")
# Versions >= MIN_DEPRECATED and < MIN_SUPPORTED are deprecated
MIN_DEPRECATED_KUBERNETES_VERSION: str = "v1.26.0"


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


def is_version_in_range(
    version: semver.VersionInfo,
    min_version: semver.VersionInfo | None,
    max_version: semver.VersionInfo | None,
) -> bool:
    """
    Check if a version is within the specified range (inclusive).

    :param version: Parsed version to check
    :param min_version: Minimum version (inclusive), None means no minimum
    :param max_version: Maximum version (inclusive), None means no maximum
    :return: True if version is in range, False otherwise
    """
    if min_version is not None and version < min_version:
        return False
    if max_version is not None and version > max_version:
        return False
    return True


def get_version_status(k8s_version: str) -> tuple[str, str | None]:
    """
    Get the status of a Kubernetes version for the current mcapi version.

    :param k8s_version: Kubernetes version (e.g., "v1.27.3")
    :return: Tuple of (status, message) where status is one of:
             VersionStatus.SUPPORTED, VersionStatus.DEPRECATED, VersionStatus.UNSUPPORTED
             and message is an optional human-readable message
    """
    # Parse the Kubernetes version
    k8s_parsed = parse_k8s_version(k8s_version)
    if k8s_parsed is None:
        return (
            VersionStatus.UNSUPPORTED,
            f"Invalid Kubernetes version format: {k8s_version}",
        )

    # Parse min/max versions
    min_supported = parse_k8s_version(MIN_SUPPORTED_KUBERNETES_VERSION)
    max_supported = parse_k8s_version(MAX_SUPPORTED_KUBERNETES_VERSION)
    min_deprecated = parse_k8s_version(MIN_DEPRECATED_KUBERNETES_VERSION)

    # Check if version is deprecated first
    # Deprecated versions are >= MIN_DEPRECATED and < MIN_SUPPORTED
    if min_deprecated is not None and min_supported is not None:
        if k8s_parsed >= min_deprecated and k8s_parsed < min_supported:
            return (
                VersionStatus.DEPRECATED,
                f"Kubernetes version {k8s_version} is deprecated. "
                f"Supported versions: {MIN_SUPPORTED_KUBERNETES_VERSION} to {MAX_SUPPORTED_KUBERNETES_VERSION}. "
                "Please upgrade to a supported version before upgrading magnum-cluster-api.",
            )

    # Check if version is in supported range
    if is_version_in_range(k8s_parsed, min_supported, max_supported):
        return VersionStatus.SUPPORTED, None

    # Version is outside supported range
    if min_supported is not None and k8s_parsed < min_supported:
        return (
            VersionStatus.UNSUPPORTED,
            f"Kubernetes version {k8s_version} is too old. "
            f"Minimum supported version is {MIN_SUPPORTED_KUBERNETES_VERSION}.",
        )

    if max_supported is not None and k8s_parsed > max_supported:
        return (
            VersionStatus.UNSUPPORTED,
            f"Kubernetes version {k8s_version} is too new. "
            f"Maximum supported version is {MAX_SUPPORTED_KUBERNETES_VERSION}.",
        )

    return (
        VersionStatus.UNSUPPORTED,
        f"Kubernetes version {k8s_version} is not supported. "
        f"Supported versions: {MIN_SUPPORTED_KUBERNETES_VERSION} to {MAX_SUPPORTED_KUBERNETES_VERSION}.",
    )


def get_supported_version_range() -> tuple[str, str]:
    """
    Get the supported Kubernetes version range for the current mcapi version.

    :return: Tuple of (min_version, max_version) (e.g., ("v1.27.0", "v1.31.0"))
    """
    return (MIN_SUPPORTED_KUBERNETES_VERSION, MAX_SUPPORTED_KUBERNETES_VERSION)


def get_deprecated_version_range() -> tuple[str, str | None]:
    """
    Get the deprecated Kubernetes version range for the current mcapi version.

    This helps operators identify clusters that may fail after an mcapi upgrade.
    Deprecated versions are from MIN_DEPRECATED up to (but not including) MIN_SUPPORTED.

    :return: Tuple of (min_deprecated, max_deprecated) where max_deprecated is None
             (deprecated range ends at MIN_SUPPORTED, exclusive)
    """
    return (MIN_DEPRECATED_KUBERNETES_VERSION, None)
