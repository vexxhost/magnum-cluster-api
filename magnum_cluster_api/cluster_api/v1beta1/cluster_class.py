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

import typing
from dataclasses import asdict as _asdict
from dataclasses import dataclass
from enum import Enum


def asdict_factory(data) -> typing.Dict[typing.Any, typing.Any]:
    """
    Convert a dataclass to a dict, converting any Enum values to their value.
    """

    def convert_value(obj):
        if isinstance(obj, Enum):
            return obj.value
        return obj

    return dict((k, convert_value(v)) for k, v in data if v is not None)


def asdict(data):
    """
    Convert a dataclass to a dict, converting any Enum values to their value.
    """

    return _asdict(data, dict_factory=asdict_factory)


class JSONSchemaPropsType(Enum):
    """
    JSONSchemaPropsType is a list of possible JSON schema value types.
    """

    ARRAY = "array"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    OBJECT = "object"
    STRING = "string"


@dataclass
class JSONSchemaProps:
    """
    JSONSchemaProps is a JSON-Schema following Specification Draft 4 (http://json-schema.org/).
    This struct has been initially copied from apiextensionsv1.JSONSchemaProps, but all fields
    which are not supported in CAPI have been removed.
    """

    type: JSONSchemaPropsType
    properties: typing.Optional[typing.Dict[str, "JSONSchemaProps"]] = None
    required: typing.Optional[typing.List[str]] = None
    items: typing.Optional["JSONSchemaProps"] = None
    enum: typing.Optional[typing.List[str]] = None
    default: typing.Optional[str] = None


@dataclass
class VariableSchema:
    """
    VariableSchema defines the schema of a variable.
    """

    openAPIV3Schema: JSONSchemaProps


@dataclass
class ClusterClassVariable:
    """
    ClusterClassVariable defines a variable which can be configured in the
    Cluster topology and used in patches.
    """

    name: str
    required: typing.Optional[bool]
    schema: VariableSchema


@dataclass
class ObjectReference:
    """
    ObjectReference contains enough information to let you inspect or modify the referred object.
    """

    apiVersion: str
    kind: str
    name: str


@dataclass
class LocalObjectTemplate:
    """
    LocalObjectTemplate defines a template for a topology Class.
    """

    ref: ObjectReference


@dataclass
class ClusterClassSpec:
    """
    ClusterClassSpec describes the desired state of the ClusterClass.
    """

    infrastructure: LocalObjectTemplate
    variables: typing.List[ClusterClassVariable]


def cluster_class_string_variable(name, required=True, enum=None, default=None):
    """
    cluster_class_string_variable returns a ClusterClassVariable with a string
    schema.
    """

    return ClusterClassVariable(
        name=name,
        required=required if required else None,
        schema=VariableSchema(
            openAPIV3Schema=JSONSchemaProps(
                type=JSONSchemaPropsType.STRING,
                enum=enum,
                default=default,
            ),
        ),
    )


def cluster_class_boolean_variable(name, required=True):
    """
    cluster_class_boolean_variable returns a ClusterClassVariable with a boolean
    schema.
    """

    return ClusterClassVariable(
        name=name,
        required=required,
        schema=VariableSchema(
            openAPIV3Schema=JSONSchemaProps(
                type=JSONSchemaPropsType.BOOLEAN,
            ),
        ),
    )


def cluster_class_array_variable(name, type=JSONSchemaPropsType.STRING, required=True):
    """
    cluster_class_array_variable returns a ClusterClassVariable with an array
    schema.
    """

    return ClusterClassVariable(
        name=name,
        required=required,
        schema=VariableSchema(
            openAPIV3Schema=JSONSchemaProps(
                type=JSONSchemaPropsType.ARRAY,
                items=JSONSchemaProps(
                    type=type,
                ),
            ),
        ),
    )


def cluster_class_object_variable(name, properties, required=True, required_items=None):
    """
    cluster_class_object_variable returns a ClusterClassVariable with an object
    schema.
    """

    if required_items is None:
        required_items = list(properties.keys())

    return ClusterClassVariable(
        name=name,
        required=required,
        schema=VariableSchema(
            openAPIV3Schema=JSONSchemaProps(
                type=JSONSchemaPropsType.OBJECT,
                required=required_items,
                properties={
                    name: JSONSchemaProps(
                        type=type,
                    )
                    if isinstance(type, JSONSchemaPropsType)
                    else type
                    for name, type in properties.items()
                },
            ),
        ),
    )
