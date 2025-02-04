# Copyright (c) 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

import typing

from attrs import asdict, define, field

from magnum_cluster_api import objects


@define
class PatchSelectorMatchMachineDeploymentClass:
    names: list[str]


@define
class PatchSelectorMatchMachinePoolClass:
    names: list[str]


@define
class PatchSelectorMatch:
    controlPlane: typing.Optional[bool] = None
    infrastructureCluster: typing.Optional[bool] = None
    machineDeploymentClass: typing.Optional[
        PatchSelectorMatchMachineDeploymentClass
    ] = None
    machinePoolClass: typing.Optional[PatchSelectorMatchMachinePoolClass] = None


@define
class PatchSelector:
    apiVersion: str
    kind: str
    matchResources: PatchSelectorMatch


@define
class JSONPatchValue:
    variable: typing.Optional[str] = None
    template: typing.Optional[str] = None


@define
class JsonPatch:
    op: str
    path: str
    value: typing.Optional[typing.Any] = field(default=None)
    valueFrom: typing.Optional[JSONPatchValue] = field(default=None)

    @value.validator
    @valueFrom.validator
    def check_xor(self, attribute, value):
        if (self.value is None) == (self.valueFrom is None):
            raise ValueError(
                "Either 'value' or 'valueFrom' must be provided, but not both."
            )


@define
class PatchDefinition:
    selector: PatchSelector
    jsonPatches: list[JsonPatch]


@define
class ClusterClassPatch:
    name: str
    enabledIf: str
    definitions: list[PatchDefinition]

    def to_dict(self):
        return asdict(self, filter=lambda attr, value: value is not None)


DISABLE_API_SERVER_FLOATING_IP = ClusterClassPatch(
    name="disableAPIServerFloatingIP",
    enabledIf="{{ if .disableAPIServerFloatingIP }}true{{end}}",
    definitions=[
        PatchDefinition(
            selector=PatchSelector(
                apiVersion=objects.OpenStackClusterTemplate.version,
                kind=objects.OpenStackClusterTemplate.kind,
                matchResources=PatchSelectorMatch(
                    infrastructureCluster=True,
                ),
            ),
            jsonPatches=[
                JsonPatch(
                    op="add",
                    path="/spec/template/spec/disableAPIServerFloatingIP",
                    valueFrom=JSONPatchValue(variable="disableAPIServerFloatingIP"),
                )
            ],
        )
    ],
)
