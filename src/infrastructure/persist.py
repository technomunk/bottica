"""
Variable persistence across multiple sessions.
"""

from __future__ import annotations

import json
import logging
from abc import ABCMeta, abstractmethod
from os.path import isfile
from typing import Any, Callable, Generic, Optional, Type, TypeVar, cast, overload

VarT = TypeVar("VarT")
_logger = logging.getLogger(__name__)


class _Missing:
    """Helper marker for undefined default parameter."""


class Persist:
    """Base class which may house PersistedVariables"""

    __metaclass__ = ABCMeta

    def __init__(self) -> None:
        self._persisted_vars: dict = {}
        self.save_on_update: bool = True

    @property
    @abstractmethod
    def filename(self) -> str:
        ...

    def save(self):
        with open(self.filename, "w") as file:
            json.dump(self._persisted_vars, file)

    def load(self):
        if isfile(self.filename):
            with open(self.filename, "r") as file:
                self._persisted_vars = json.load(file)

    def _update(self):
        if self.save_on_update:
            self.save()


class Serializer(Generic[VarT]):
    """Basic interface for converting a complex type to something that is JSON-serializeable."""

    def finalize(self, **kwargs):
        """
        More complex serializers may require extra metadata and thus the Persist
        derivate may invoke finalize() before from_json() is ever called
        """

    def to_json(self, variable: VarT) -> Any:
        """Return something that is hopefully serializeable."""
        return variable

    def from_json(self, variable: Any) -> VarT:
        """Perform the reverse of marshal operation."""
        return variable


class PersistedVar(Generic[VarT]):
    """
    An descriptor for a class field that is in reality a member of a dictionary.
    """

    def __init__(
        self,
        default_value: VarT | _Missing = _Missing(),
        *,
        default_factory: Optional[Callable[[], VarT]] = None,
        serializer: Serializer[VarT] = Serializer(),  # type: ignore
    ) -> None:
        if default_factory is not None:
            self.default: Optional[Callable[[], VarT]] = default_factory
        elif isinstance(default_value, _Missing):
            self.default = None
        else:
            self.default = lambda: cast(VarT, default_value)

        self.serializer = serializer

    def __set_name__(self, owner: Type[Persist], name: str):
        if not issubclass(owner, Persist):
            raise TypeError("PersistVar has to be a class-variable of a Persist-derived class")

        self._name = name

    @overload
    def __get__(self, instance: Persist, owner: Optional[Type[Persist]]) -> VarT:
        pass

    @overload
    def __get__(self, instance: None, owner: None) -> PersistedVar[VarT]:
        pass

    @overload
    def __get__(self, instance: None, owner: Type[Persist]) -> PersistedVar[VarT]:
        pass

    def __get__(
        self,
        instance: Optional[Persist],
        owner: Optional[Type[Persist]] = None,
    ) -> VarT | PersistedVar[VarT]:
        # Allow class-level access to the descriptor for further modification
        if instance is None:
            return self

        if self.default is not None and self._name not in instance._persisted_vars:
            instance._persisted_vars[self._name] = self.serializer.to_json(self.default())
        return self.serializer.from_json(instance._persisted_vars[self._name])

    def __set__(self, instance: Persist, value: VarT):
        new_value = self.serializer.to_json(value)
        if (
            self._name not in instance._persisted_vars
            or instance._persisted_vars[self._name] != new_value
        ):
            instance._persisted_vars[self._name] = new_value
            instance._update()

    def __delete__(self, instance: Persist):
        del instance._persisted_vars[self._name]
