"""Helpers for serialization/Pydantic things."""

import json
from typing import Annotated

import numpy
from openff.models.types.unit_types import NanometerQuantity
from openff.toolkit import Quantity, Topology, unit
from pydantic import (
    PlainSerializer,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    WrapSerializer,
    WrapValidator,
)

from openff.interchange.exceptions import InvalidBoxError


def _topology_custom_before_validator(
    topology: str | Topology,
    handler: ValidatorFunctionWrapHandler,
    info: ValidationInfo,
) -> Topology:
    if info.mode == "json":
        # Making a new one so no need to deepcopy
        return handler(Topology.from_json(topology))

    assert info.mode == "python"
    if isinstance(topology, Topology):
        return Topology(topology)
    elif isinstance(topology, str):
        return Topology.from_json(topology)
    else:
        raise Exception(f"Failed to convert topology of type {type(topology)}")


def _topology_json_serializer(
    topology: Topology,
    nxt: SerializerFunctionWrapHandler,
) -> str:
    return topology.to_json()


def _topology_dict_serializer(topology: Topology) -> dict:
    return topology.to_dict()


_AnnotatedTopology = Annotated[
    Topology,
    WrapValidator(_topology_custom_before_validator),
    PlainSerializer(_topology_dict_serializer, return_type=dict),
    WrapSerializer(_topology_json_serializer, when_used="json"),
]


def box_validator(
    value: str | Quantity,
    handler: ValidatorFunctionWrapHandler,
    info: ValidationInfo,
) -> Quantity:
    """Validate a box vector."""
    if info.mode == "json":
        if isinstance(value, Quantity):
            return handler(value)
        elif isinstance(value, str):
            tmp = json.loads(value)
            return handler(Quantity(tmp["val"], unit.Unit(tmp["unit"])))
        else:
            return handler(NanometerQuantity.__call__(value))

    assert info.mode == "python"

    if isinstance(value, Quantity):
        pass
    elif isinstance(value, str):
        tmp = json.loads(value)
        value = Quantity(tmp["val"], unit.Unit(tmp["unit"]))
    else:
        raise Exception()

    dimensions = numpy.atleast_2d(value).shape

    if dimensions == (3, 3):
        return value
    elif dimensions in ((1, 3), (3, 1)):
        return value * numpy.eye(3)
    else:
        raise InvalidBoxError(
            f"Failed to convert value {value} to 3x3 box vectors. Please file an issue if you think this "
            "input should be supported and the failure is an error.",
        )


_AnnotatedBox = Annotated[
    NanometerQuantity,
    WrapValidator(box_validator),
]


def positions_validator(
    value: str | Quantity,
    handler: ValidatorFunctionWrapHandler,
    info: ValidationInfo,
) -> Quantity:
    """Validate positions."""
    if info.mode == "json":
        if isinstance(value, Quantity):
            return handler(value)
        elif isinstance(value, str):
            tmp = json.loads(value)
            return handler(Quantity(tmp["val"], unit.Unit(tmp["unit"])))
        else:
            return handler(NanometerQuantity.__call__(value))

    assert info.mode == "python"

    if isinstance(value, Quantity):
        return value
    elif isinstance(value, str):
        tmp = json.loads(value)
        return Quantity(tmp["val"], unit.Unit(tmp["unit"]))
    else:
        raise Exception


_AnnotatedPositions = Annotated[
    NanometerQuantity,
    WrapValidator(positions_validator),
]
