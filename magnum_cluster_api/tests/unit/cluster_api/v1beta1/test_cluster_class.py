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

from magnum_cluster_api import utils
from magnum_cluster_api.cluster_api.v1beta1 import cluster_class


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
