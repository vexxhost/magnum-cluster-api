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

import pykube

from magnum_cluster_api import utils
from magnum_cluster_api.cluster_api.v1beta1 import cluster_class


def test_cluster_class_asdict():
    spec = cluster_class.asdict(
        cluster_class.ClusterClassSpec(
            variables=[
                cluster_class.cluster_class_object_variable(
                    name="apiServerLoadBalancer",
                    properties={
                        "enabled": cluster_class.JSONSchemaPropsType.BOOLEAN,
                    },
                ),
                cluster_class.cluster_class_string_variable(
                    name="apiServerTLSCipherSuites",
                ),
                cluster_class.cluster_class_object_variable(
                    name="openidConnect",
                    properties={
                        "issuerUrl": cluster_class.JSONSchemaPropsType.STRING,
                        "clientId": cluster_class.JSONSchemaPropsType.STRING,
                        "usernameClaim": cluster_class.JSONSchemaPropsType.STRING,
                        "usernamePrefix": cluster_class.JSONSchemaPropsType.STRING,
                        "groupsClaim": cluster_class.JSONSchemaPropsType.STRING,
                        "groupsPrefix": cluster_class.JSONSchemaPropsType.STRING,
                    },
                ),
                cluster_class.cluster_class_object_variable(
                    name="auditLog",
                    properties={
                        "enabled": cluster_class.JSONSchemaPropsType.BOOLEAN,
                        "maxAge": cluster_class.JSONSchemaPropsType.STRING,
                        "maxBackup": cluster_class.JSONSchemaPropsType.STRING,
                        "maxSize": cluster_class.JSONSchemaPropsType.STRING,
                    },
                ),
                cluster_class.cluster_class_object_variable(
                    name="bootVolume",
                    required_items=["size"],
                    properties={
                        "size": cluster_class.JSONSchemaPropsType.INTEGER,
                        "type": cluster_class.JSONSchemaPropsType.STRING,
                    },
                ),
                cluster_class.cluster_class_object_variable(
                    name="clusterIdentityRef",
                    properties={
                        "kind": cluster_class.JSONSchemaProps(
                            type=cluster_class.JSONSchemaPropsType.STRING,
                            enum=[pykube.Secret.kind],
                        ),
                        "name": cluster_class.JSONSchemaPropsType.STRING,
                    },
                ),
                cluster_class.cluster_class_string_variable(
                    name="cloudCaCert",
                ),
                cluster_class.cluster_class_string_variable(
                    name="cloudControllerManagerConfig",
                ),
                cluster_class.cluster_class_string_variable(
                    name="containerdConfig",
                ),
                cluster_class.cluster_class_string_variable(
                    name="controlPlaneFlavor",
                ),
                cluster_class.cluster_class_boolean_variable(
                    name="disableAPIServerFloatingIP",
                ),
                cluster_class.cluster_class_array_variable(
                    name="dnsNameservers",
                ),
                cluster_class.cluster_class_string_variable(
                    name="externalNetworkId",
                ),
                cluster_class.cluster_class_string_variable(
                    name="fixedNetworkName",
                ),
                cluster_class.cluster_class_string_variable(name="fixedSubnetId"),
                cluster_class.cluster_class_string_variable(
                    name="flavor",
                ),
                cluster_class.cluster_class_string_variable(
                    name="imageRepository",
                ),
                cluster_class.cluster_class_string_variable(
                    name="imageUUID",
                ),
                cluster_class.cluster_class_string_variable(
                    name="kubeletTLSCipherSuites",
                ),
                cluster_class.cluster_class_string_variable(
                    name="nodeCidr",
                ),
                cluster_class.cluster_class_string_variable(
                    name="sshKeyName",
                    required=False,
                ),
                cluster_class.cluster_class_string_variable(
                    name="operatingSystem",
                    enum=utils.AVAILABLE_OPERATING_SYSTEMS,
                    default="ubuntu",
                ),
            ]
        )
    )

    assert spec["variables"] == [
        {
            "name": "apiServerLoadBalancer",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "object",
                    "required": ["enabled"],
                    "properties": {
                        "enabled": {
                            "type": "boolean",
                        },
                    },
                },
            },
        },
        {
            "name": "apiServerTLSCipherSuites",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "openidConnect",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "object",
                    "required": [
                        "issuerUrl",
                        "clientId",
                        "usernameClaim",
                        "usernamePrefix",
                        "groupsClaim",
                        "groupsPrefix",
                    ],
                    "properties": {
                        "issuerUrl": {
                            "type": "string",
                        },
                        "clientId": {
                            "type": "string",
                        },
                        "usernameClaim": {
                            "type": "string",
                        },
                        "usernamePrefix": {
                            "type": "string",
                        },
                        "groupsClaim": {
                            "type": "string",
                        },
                        "groupsPrefix": {
                            "type": "string",
                        },
                    },
                },
            },
        },
        {
            "name": "auditLog",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "object",
                    "required": [
                        "enabled",
                        "maxAge",
                        "maxBackup",
                        "maxSize",
                    ],
                    "properties": {
                        "enabled": {
                            "type": "boolean",
                        },
                        "maxAge": {
                            "type": "string",
                        },
                        "maxBackup": {
                            "type": "string",
                        },
                        "maxSize": {
                            "type": "string",
                        },
                    },
                },
            },
        },
        {
            "name": "bootVolume",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "object",
                    "required": ["size"],
                    "properties": {
                        "size": {
                            "type": "integer",
                        },
                        "type": {
                            "type": "string",
                        },
                    },
                },
            },
        },
        {
            "name": "clusterIdentityRef",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "object",
                    "required": ["kind", "name"],
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": [pykube.Secret.kind],
                        },
                        "name": {"type": "string"},
                    },
                },
            },
        },
        {
            "name": "cloudCaCert",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "cloudControllerManagerConfig",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "containerdConfig",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "controlPlaneFlavor",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "disableAPIServerFloatingIP",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "boolean",
                },
            },
        },
        {
            "name": "dnsNameservers",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
        },
        {
            "name": "externalNetworkId",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "fixedNetworkName",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "fixedSubnetId",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "flavor",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "imageRepository",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "imageUUID",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "kubeletTLSCipherSuites",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "nodeCidr",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "sshKeyName",
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                },
            },
        },
        {
            "name": "operatingSystem",
            "required": True,
            "schema": {
                "openAPIV3Schema": {
                    "type": "string",
                    "enum": utils.AVAILABLE_OPERATING_SYSTEMS,
                    "default": "ubuntu",
                },
            },
        },
    ]


def test_cluster_class_string_variable():
    assert cluster_class.asdict(
        cluster_class.cluster_class_string_variable(
            name="controlPlaneFlavor",
        )
    ) == {
        "name": "controlPlaneFlavor",
        "required": True,
        "schema": {
            "openAPIV3Schema": {
                "type": "string",
            },
        },
    }


def test_cluster_class_string_variable_with_enum_and_default():
    assert cluster_class.asdict(
        cluster_class.cluster_class_string_variable(
            name="operatingSystem",
            enum=utils.AVAILABLE_OPERATING_SYSTEMS,
            default="ubuntu",
        )
    ) == {
        "name": "operatingSystem",
        "required": True,
        "schema": {
            "openAPIV3Schema": {
                "type": "string",
                "enum": utils.AVAILABLE_OPERATING_SYSTEMS,
                "default": "ubuntu",
            },
        },
    }


def test_cluster_class_boolean_variable():
    assert cluster_class.asdict(
        cluster_class.cluster_class_boolean_variable(
            name="disableAPIServerFloatingIP",
        )
    ) == {
        "name": "disableAPIServerFloatingIP",
        "required": True,
        "schema": {
            "openAPIV3Schema": {
                "type": "boolean",
            },
        },
    }


def test_cluster_class_array_string_variable():
    assert cluster_class.asdict(
        cluster_class.cluster_class_array_variable(
            name="dnsNameservers",
        )
    ) == {
        "name": "dnsNameservers",
        "required": True,
        "schema": {
            "openAPIV3Schema": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
    }


def test_cluster_class_object_variable():
    assert cluster_class.asdict(
        cluster_class.cluster_class_object_variable(
            name="apiServerLoadBalancer",
            properties={
                "enabled": cluster_class.JSONSchemaPropsType.BOOLEAN,
            },
        )
    ) == {
        "name": "apiServerLoadBalancer",
        "required": True,
        "schema": {
            "openAPIV3Schema": {
                "type": "object",
                "required": ["enabled"],
                "properties": {
                    "enabled": {
                        "type": "boolean",
                    },
                },
            },
        },
    }
