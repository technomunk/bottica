"""
Variable persistence across multiple sessions.

A Field is a descriptor for a variable that is picked to a file
if the owning object's save() method is called.

All fields can be populated with data from file by using Persist.load method.
"""

from __future__ import annotations

import logging
import pickle
from os import path
from typing import Any, Callable, ClassVar, Generic, List, Optional, Type, TypeVar, cast, overload

VarT = TypeVar("VarT")
SerialT = TypeVar("SerialT")
ClassT = TypeVar("ClassT", bound=object)
_logger = logging.getLogger(__name__)


class _Missing:
    """Helper marker for undefined default parameter."""


# This is an interface, so we need self and kwargs for API
# pylint: disable=unused-argument
class Converter(Generic[VarT]):
    """Convert data to and from form that is saved to file."""

    def to_serial(self, value: VarT, **kwargs) -> Any:
        return value

    async def from_serial(self, value: Any, **kwargs) -> VarT:
        return value


class Persist:
    """
    A persistable object that can save persist.Field values.

    Should be the base class of any class that defines Fields for the persistence mechanism to work.
    """

    _persist_fields: ClassVar[List[Field]] = []
    _persist_values: dict

    def __init__(self) -> None:
        self._persist_values = {}

    def save(self, filename: str, **converter_kwargs) -> None:
        """
        Save all _persist_fields to provided file.

        Provided converters will be invoked for each field value that is of the relevant type.
        """
        marshalled_data = {}
        for field in self._persist_fields:
            value = getattr(self, field.name)
            marshalled_data[field.name] = field.converter.to_serial(value, **converter_kwargs)

        with open(filename, "wb") as pickle_file:
            pickle.dump(marshalled_data, pickle_file)

        _logger.debug("saved %s", filename)

    async def load(self, filename: str, **converter_kwargs) -> None:
        """
        Load as many _persist_fields from provided file as possible.

        If the file does not exist all fields with default values will receive said default values.
        Provided converters will be invoked for each field of relevant type.
        """
        marshalled_data = {}
        if path.isfile(filename):
            with open(filename, "rb") as pickle_file:
                marshalled_data = pickle.load(pickle_file)

        for field in self._persist_fields:
            if field.name in marshalled_data:
                value = marshalled_data[field.name]
                value = await field.converter.from_serial(value, **converter_kwargs)
                setattr(self, field.name, value)
            elif field.default:
                setattr(self, field.name, field.default())


class Field(Generic[VarT]):
    """
    An descriptor for a class field that is in reality a member of a dictionary.
    """

    __slots__ = "name", "default", "converter"

    def __init__(
        self,
        default: VarT | _Missing = _Missing(),
        *,
        default_factory: Optional[Callable[[], VarT]] = None,
        converter: Converter[VarT] = Converter(),
    ) -> None:
        self.name: str
        if isinstance(default, _Missing):
            self.default: Optional[Callable[[], VarT]] = default_factory
        elif default_factory is not None:
            raise ValueError("cannot specify both default and default_factory")
        else:
            self.default = lambda: cast(VarT, default)
        self.converter = converter

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
