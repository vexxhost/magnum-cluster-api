# SPDX-FileCopyrightText: © 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Test cases for go_template module.

These test cases are based on all enabled_if expressions found in src/features/*.rs
"""

from typing import Any, Dict

import pytest

from magnum_cluster_api.tests.unit.go_template import render


@pytest.mark.parametrize(
    "template,data,expected",
    [
        # admission_plugins
        pytest.param(
            "{{ if .admissionControlList }}true{{end}}",
            {},
            "",
            id="admission_list_missing",
        ),
        pytest.param(
            "{{ if .admissionControlList }}true{{end}}",
            {"admissionControlList": None},
            "",
            id="admission_list_none",
        ),
        pytest.param(
            "{{ if .admissionControlList }}true{{end}}",
            {"admissionControlList": []},
            "",
            id="admission_list_empty",
        ),
        pytest.param(
            "{{ if .admissionControlList }}true{{end}}",
            {"admissionControlList": ["single"]},
            "true",
            id="admission_list_single",
        ),
        pytest.param(
            "{{ if .admissionControlList }}true{{end}}",
            {"admissionControlList": ["plugin1", "plugin2"]},
            "true",
            id="admission_list_multiple",
        ),
        # api_server_floating_ip
        pytest.param(
            '{{ if ne .apiServerFloatingIP "" }}true{{end}}',
            {},
            "true",
            id="api_floating_ip_missing",  # None != ""
        ),
        pytest.param(
            '{{ if ne .apiServerFloatingIP "" }}true{{end}}',
            {"apiServerFloatingIP": ""},
            "",
            id="api_floating_ip_empty",
        ),
        pytest.param(
            '{{ if ne .apiServerFloatingIP "" }}true{{end}}',
            {"apiServerFloatingIP": "10.0.0.1"},
            "true",
            id="api_floating_ip_present",
        ),
        # audit_log
        pytest.param(
            "{{ if .auditLog.enabled }}true{{end}}", {}, "", id="audit_log_missing"
        ),
        pytest.param(
            "{{ if .auditLog.enabled }}true{{end}}",
            {"auditLog": {"enabled": False}},
            "",
            id="audit_log_disabled",
        ),
        pytest.param(
            "{{ if .auditLog.enabled }}true{{end}}",
            {"auditLog": {"enabled": True}},
            "true",
            id="audit_log_enabled",
        ),
        # boot_volume
        pytest.param(
            "{{ if gt .bootVolume.size 0.0 }}true{{end}}",
            {},
            "",
            id="boot_volume_missing",
        ),
        pytest.param(
            "{{ if gt .bootVolume.size 0.0 }}true{{end}}",
            {"bootVolume": {"size": 0.0}},
            "",
            id="boot_volume_0",
        ),
        pytest.param(
            "{{ if gt .bootVolume.size 0.0 }}true{{end}}",
            {"bootVolume": {"size": -1.0}},
            "",
            id="boot_volume_negative",
        ),
        pytest.param(
            "{{ if gt .bootVolume.size 0.0 }}true{{end}}",
            {"bootVolume": {"size": 0.1}},
            "true",
            id="boot_volume_0.1",
        ),
        pytest.param(
            "{{ if gt .bootVolume.size 0.0 }}true{{end}}",
            {"bootVolume": {"size": 10.0}},
            "true",
            id="boot_volume_10",
        ),
        # cloud_provider
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {},
            "false",
            id="cloud_provider_missing",
        ),
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {"builtin": {"controlPlane": {"version": None}}},
            "false",
            id="cloud_provider_none",
        ),
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {"builtin": {"controlPlane": {"version": ""}}},
            "false",
            id="cloud_provider_empty",
        ),
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {"builtin": {"controlPlane": {"version": "v1.28.0"}}},
            "true",
            id="cloud_provider_v1.28.0",
        ),
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {"builtin": {"controlPlane": {"version": "v1.32.9"}}},
            "true",
            id="cloud_provider_v1.32.9",
        ),
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {"builtin": {"controlPlane": {"version": "v1.33.0"}}},
            "false",
            id="cloud_provider_v1.33.0",
        ),
        pytest.param(
            '{{ semverCompare "<1.33.0" .builtin.controlPlane.version }}',
            {"builtin": {"controlPlane": {"version": "v1.34.0"}}},
            "false",
            id="cloud_provider_v1.34.0",
        ),
        # control_plane_availability_zones
        pytest.param(
            '{{ if ne (index .controlPlaneAvailabilityZones 0) "" }}true{{end}}',
            {},
            "true",
            id="control_plane_az_missing",
        ),
        pytest.param(
            '{{ if ne (index .controlPlaneAvailabilityZones 0) "" }}true{{end}}',
            {"controlPlaneAvailabilityZones": None},
            "true",
            id="control_plane_az_none",
        ),
        pytest.param(
            '{{ if ne (index .controlPlaneAvailabilityZones 0) "" }}true{{end}}',
            {"controlPlaneAvailabilityZones": []},
            "true",
            id="control_plane_az_empty_list",
        ),
        pytest.param(
            '{{ if ne (index .controlPlaneAvailabilityZones 0) "" }}true{{end}}',
            {"controlPlaneAvailabilityZones": [""]},
            "",
            id="control_plane_az_empty_string",
        ),
        pytest.param(
            '{{ if ne (index .controlPlaneAvailabilityZones 0) "" }}true{{end}}',
            {"controlPlaneAvailabilityZones": ["zone1"]},
            "true",
            id="control_plane_az_single",
        ),
        pytest.param(
            '{{ if ne (index .controlPlaneAvailabilityZones 0) "" }}true{{end}}',
            {"controlPlaneAvailabilityZones": ["zone1", "zone2", "zone3"]},
            "true",
            id="control_plane_az_multiple",
        ),
        # disable_api_server_floating_ip
        pytest.param(
            "{{ if .disableAPIServerFloatingIP }}true{{end}}",
            {},
            "",
            id="disable_api_floating_ip_missing",
        ),
        pytest.param(
            "{{ if .disableAPIServerFloatingIP }}true{{end}}",
            {"disableAPIServerFloatingIP": False},
            "",
            id="disable_api_floating_ip_false",
        ),
        pytest.param(
            "{{ if .disableAPIServerFloatingIP }}true{{end}}",
            {"disableAPIServerFloatingIP": True},
            "true",
            id="disable_api_floating_ip_true",
        ),
        # image_repository
        pytest.param(
            '{{ if ne .imageRepository "" }}true{{end}}',
            {},
            "true",
            id="image_repo_missing",  # None != ""
        ),
        pytest.param(
            '{{ if ne .imageRepository "" }}true{{end}}',
            {"imageRepository": ""},
            "",
            id="image_repo_empty",
        ),
        pytest.param(
            '{{ if ne .imageRepository "" }}true{{end}}',
            {"imageRepository": "docker.io/library"},
            "true",
            id="image_repo_present",
        ),
        # keystone_auth
        pytest.param(
            "{{ if .enableKeystoneAuth }}true{{end}}",
            {},
            "",
            id="keystone_auth_missing",
        ),
        pytest.param(
            "{{ if .enableKeystoneAuth }}true{{end}}",
            {"enableKeystoneAuth": False},
            "",
            id="keystone_auth_disabled",
        ),
        pytest.param(
            "{{ if .enableKeystoneAuth }}true{{end}}",
            {"enableKeystoneAuth": True},
            "true",
            id="keystone_auth_enabled",
        ),
        # networks
        pytest.param(
            '{{ if eq .fixedNetworkId "" }}true{{end}}',
            {},
            "",
            id="networks_fixed_network_eq_missing",
        ),
        pytest.param(
            '{{ if eq .fixedNetworkId "" }}true{{end}}',
            {"fixedNetworkId": ""},
            "true",
            id="networks_fixed_network_eq_empty",
        ),
        pytest.param(
            '{{ if eq .fixedNetworkId "" }}true{{end}}',
            {"fixedNetworkId": "network-123"},
            "",
            id="networks_fixed_network_eq_not_empty",
        ),
        pytest.param(
            '{{ if ne .fixedNetworkId "" }}true{{end}}',
            {},
            "true",
            id="networks_fixed_network_ne_missing",
        ),
        pytest.param(
            '{{ if ne .fixedNetworkId "" }}true{{end}}',
            {"fixedNetworkId": ""},
            "",
            id="networks_fixed_network_ne_empty",
        ),
        pytest.param(
            '{{ if ne .fixedNetworkId "" }}true{{end}}',
            {"fixedNetworkId": "network-123"},
            "true",
            id="networks_fixed_network_ne_present",
        ),
        pytest.param(
            '{{ if ne .fixedSubnetId "" }}true{{end}}',
            {},
            "true",
            id="networks_fixed_subnet_missing",
        ),
        pytest.param(
            '{{ if ne .fixedSubnetId "" }}true{{end}}',
            {"fixedSubnetId": ""},
            "",
            id="networks_fixed_subnet_empty",
        ),
        pytest.param(
            '{{ if ne .fixedSubnetId "" }}true{{end}}',
            {"fixedSubnetId": "subnet-123"},
            "true",
            id="networks_fixed_subnet_present",
        ),
        # openid_connect
        pytest.param(
            "{{ if .openidConnect.issuerUrl }}true{{end}}",
            {},
            "",
            id="openid_issuer_missing",
        ),
        pytest.param(
            "{{ if .openidConnect.issuerUrl }}true{{end}}",
            {"openidConnect": {"issuerUrl": ""}},
            "",
            id="openid_issuer_empty",
        ),
        pytest.param(
            "{{ if .openidConnect.issuerUrl }}true{{end}}",
            {"openidConnect": {"issuerUrl": "https://example.com"}},
            "true",
            id="openid_issuer_present",
        ),
        # operating_system
        pytest.param(
            '{{ if eq .operatingSystem "ubuntu" }}true{{end}}',
            {"operatingSystem": "flatcar"},
            "",
            id="os_ubuntu_no_match",
        ),
        pytest.param(
            '{{ if eq .operatingSystem "ubuntu" }}true{{end}}',
            {"operatingSystem": "ubuntu"},
            "true",
            id="os_ubuntu_matches",
        ),
        pytest.param(
            '{{ if eq .operatingSystem "flatcar" }}true{{end}}',
            {"operatingSystem": "ubuntu"},
            "",
            id="os_flatcar_no_match",
        ),
        pytest.param(
            '{{ if eq .operatingSystem "flatcar" }}true{{end}}',
            {"operatingSystem": "flatcar"},
            "true",
            id="os_flatcar_matches",
        ),
        # volumes
        pytest.param(
            "{{ if or .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": False, "enableDockerVolume": False},
            "",
            id="volumes_or_none",
        ),
        pytest.param(
            "{{ if or .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": True, "enableDockerVolume": False},
            "true",
            id="volumes_or_etcd_only",
        ),
        pytest.param(
            "{{ if or .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": False, "enableDockerVolume": True},
            "true",
            id="volumes_or_docker_only",
        ),
        pytest.param(
            "{{ if or .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": True, "enableDockerVolume": True},
            "true",
            id="volumes_or_both",
        ),
        pytest.param(
            "{{ if .enableDockerVolume }}true{{ end }}",
            {},
            "",
            id="volumes_docker_volume_missing",
        ),
        pytest.param(
            "{{ if .enableDockerVolume }}true{{ end }}",
            {"enableDockerVolume": False},
            "",
            id="volumes_docker_volume_disabled",
        ),
        pytest.param(
            "{{ if .enableDockerVolume }}true{{ end }}",
            {"enableDockerVolume": True},
            "true",
            id="volumes_docker_volume_enabled",
        ),
        pytest.param(
            "{{ if .enableEtcdVolume }}true{{ end }}",
            {},
            "",
            id="volumes_etcd_volume_missing",
        ),
        pytest.param(
            "{{ if .enableEtcdVolume }}true{{ end }}",
            {"enableEtcdVolume": False},
            "",
            id="volumes_etcd_volume_disabled",
        ),
        pytest.param(
            "{{ if .enableEtcdVolume }}true{{ end }}",
            {"enableEtcdVolume": True},
            "true",
            id="volumes_etcd_volume_enabled",
        ),
        pytest.param(
            "{{ if and .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": False, "enableDockerVolume": False},
            "",
            id="volumes_and_none",
        ),
        pytest.param(
            "{{ if and .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": True, "enableDockerVolume": False},
            "",
            id="volumes_and_etcd_only",
        ),
        pytest.param(
            "{{ if and .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": False, "enableDockerVolume": True},
            "",
            id="volumes_and_docker_only",
        ),
        pytest.param(
            "{{ if and .enableEtcdVolume .enableDockerVolume }}true{{ end }}",
            {"enableEtcdVolume": True, "enableDockerVolume": True},
            "true",
            id="volumes_and_both",
        ),
        pytest.param(
            "{{ if and .enableDockerVolume (not .enableEtcdVolume) }}true{{ end }}",
            {"enableDockerVolume": False, "enableEtcdVolume": False},
            "",
            id="volumes_docker_not_etcd_neither",
        ),
        pytest.param(
            "{{ if and .enableDockerVolume (not .enableEtcdVolume) }}true{{ end }}",
            {"enableDockerVolume": True, "enableEtcdVolume": True},
            "",
            id="volumes_docker_not_etcd_both",
        ),
        pytest.param(
            "{{ if and .enableDockerVolume (not .enableEtcdVolume) }}true{{ end }}",
            {"enableDockerVolume": True, "enableEtcdVolume": False},
            "true",
            id="volumes_docker_not_etcd_true",
        ),
    ],
)
def test_enabled_if_expressions(
    template: str, data: Dict[str, Any], expected: str
) -> None:
    """Test enabled_if expressions with various inputs."""
    assert render(template, data) == expected
