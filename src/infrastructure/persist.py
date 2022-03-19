"""
Variable persistence across multiple sessions.
"""

from __future__ import annotations

import json
import logging
from inspect import get_annotations, isawaitable, iscoroutine
from os import path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    cast,
    overload,
)

from .converters import identity

VarT = TypeVar("VarT")
ClassT = TypeVar("ClassT", bound=object)
_logger = logging.getLogger(__name__)


class _Missing:
    """Helper marker for undefined default parameter."""


class Persist:
    """A persistable object that can save persist.Field values."""

    _persist_fields: ClassVar[List[Field]] = []

    def __init__(self) -> None:
        self._persist_values: dict = {}

    def save(self, filename: str, converters: Dict[Type, Callable[[Any], Any]] = {}) -> None:
        """
        Save all _persist_fields to provided file.

        Provided converters will be invoked for each field value that is of the relevant type.
        """
        marshalled_data = {}
        for field in self._persist_fields:
            value = getattr(self, field.name)
            converter = converters.get(type(value), identity)
            marshalled_data[field.name] = converter(value)

        with open(filename, "w") as json_file:
            json.dump(marshalled_data, json_file)

    async def load(self, filename: str, converters: Dict[Type, Callable[[Any], Any]] = {}) -> None:
        """
        Load as many _persist_fields from provided file as possible.

        Provided converters will be invoked for each field of relevant type.
        """
        marshalled_data = {}
        if path.isfile(filename):
            with open(filename, "r") as json_file:
                marshalled_data = json.load(json_file)

        for field in self._persist_fields:
            if field.name in marshalled_data:
                converter = converters.get(field.type, field.type)
                value = converter(marshalled_data[field.name])

                if isawaitable(value):
                    value = await value
                setattr(self, field.name, value)
            elif field.default:
                setattr(self, field.name, field.default())


class Field(Generic[VarT]):
    """
    An descriptor for a class field that is in reality a member of a dictionary.
    """

    __slots__ = "name", "type", "default"

    def __init__(
        self,
        default: VarT | _Missing = _Missing(),
        *,
        default_factory: Optional[Callable[[], VarT]] = None,
        type_: Type[VarT] | _Missing = _Missing(),
    ) -> None:
        self.type: Type[VarT] = type_  # type: ignore
        if isinstance(default, _Missing):
            self.default: Optional[Callable[[], VarT]] = default_factory
        elif default_factory is not None:
            raise ValueError("cannot specify both default and default_factory")
        else:
            self.default = lambda: cast(VarT, default)
            if isinstance(type_, _Missing):
                self.type = type(default)

    def __set_name__(self, owner: Type[Persist], name: str) -> None:
        owner._persist_fields.append(self)
        self.name = name

    @overload
    def __get__(self, instance: None, owner: Type[Persist]) -> Field[VarT]:
        ...

    @overload
    def __get__(self, instance: Persist, owner: Optional[Type[Persist]]) -> VarT:
        ...

    def __get__(
        self,
        instance: Optional[Persist],
        owner: Optional[Type[Persist]] = None,
    ) -> VarT | Field[VarT]:
        if instance is None:
            return self

        if self.name not in instance._persist_values and self.default:
            instance._persist_values[self.name] = self.default()
        return instance._persist_values[self.name]

    def __set__(self, instance: Persist, value: VarT):
        instance._persist_values[self.name] = value


def infer_field_types(cls: Type[Persist]) -> Type[Persist]:
    cls_annotations = get_annotations(cls, eval_str=True)

    for field in cls._persist_fields:
        if field.name in cls_annotations:
            field.type = cls_annotations[field.name]
            # make sure explicitly marked fields get correct type hint
            if vars(field.type).get("__origin__") == Field:
                field.type = vars(field.type)["__args__"][0]
        elif isinstance(field.type, _Missing):
            if field.name not in cls_annotations:
                raise TypeError("field is missing type info", field.name)

    return cls
