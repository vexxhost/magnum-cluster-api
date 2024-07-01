# Copyright (c) 2024 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class OpenAPIV3SchemaType(str, Enum):
    ARRAY: str = "array"
    BOOLEAN: str = "boolean"
    INTEGER: str = "integer"
    OBJECT: str = "object"
    STRING: str = "string"


class OpenAPIV3Schema(BaseModel):
    type: OpenAPIV3SchemaType


class OpenAPIV3ArraySchema(OpenAPIV3Schema):
    type: OpenAPIV3SchemaType = OpenAPIV3SchemaType.ARRAY
    default: Optional[List[Any]] = None
    items: OpenAPIV3Schema


class OpenAPIV3BooleanSchema(OpenAPIV3Schema):
    type: OpenAPIV3SchemaType = OpenAPIV3SchemaType.BOOLEAN
    default: Optional[bool] = None


class OpenAPIV3IntegerSchema(OpenAPIV3Schema):
    type: OpenAPIV3SchemaType = OpenAPIV3SchemaType.INTEGER
    default: Optional[int] = None


class OpenAPIV3ObjectSchema(OpenAPIV3Schema):
    type: OpenAPIV3SchemaType = OpenAPIV3SchemaType.OBJECT
    default: Optional[Dict[str, Any]] = None
    required: Optional[List[str]] = None
    properties: Dict[str, OpenAPIV3Schema]


class OpenAPIV3StringSchema(OpenAPIV3Schema):
    type: OpenAPIV3SchemaType = OpenAPIV3SchemaType.STRING
    default: Optional[str] = None
    enum: Optional[List[str]] = None


class VariableSchema(BaseModel):
    openAPIV3Schema: OpenAPIV3Schema


class Variable(BaseModel):
    name: str
    required: Optional[bool] = None
    schema: VariableSchema
