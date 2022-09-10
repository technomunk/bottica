"""
Decriptor-based validators for generic data with static duck-typing support.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Any, Generic, Protocol, Type, TypeVar, overload

from .friendly_error import FriendlyError


class SupportsLT(Protocol):
    @abstractmethod
    def __lt__(self, other: Any) -> bool:
        ...


VarT = TypeVar("VarT")
LessThanT = TypeVar("LessThanT", bound=SupportsLT)


class ValidationError(FriendlyError):
    """An error to prevent an invalid configuration value."""


class Validator(Generic[VarT], metaclass=ABCMeta):
    def __init__(self, default: VarT) -> None:
        self.name: str
        self.default = default

    def __set_name__(self, owner: Type, name: str) -> None:
        self.name = "__" + name

    @overload
    def __get__(self, instance: None, owner: Any) -> Validator[VarT]:
        ...

    @overload
    def __get__(self, instance: Any, owner: Any) -> VarT:
        ...

    def __get__(self, instance: Any, owner: Any) -> VarT | Validator[VarT]:
        if instance is None:
            return self

        if not hasattr(instance, self.name):
            setattr(instance, self.name, self.default)

        return getattr(instance, self.name)

    def __set__(self, instance: Any, value: VarT) -> None:
        self.validate(value)
        setattr(instance, self.name, value)

    @abstractmethod
    def validate(self, value: VarT) -> None:
        ...


class MinMax(Validator[LessThanT]):
    def __init__(self, default: LessThanT, min_val: LessThanT, max_val: LessThanT) -> None:
        super().__init__(default)
        self.min = min_val
        self.max = max_val

    def validate(self, value: LessThanT) -> None:
        if value < self.min or self.max < value:
            raise ValidationError(f"Provided value has to be between {self.min} and {self.max}")


class Min(Validator[LessThanT]):
    def __init__(self, default: LessThanT, min_val: LessThanT) -> None:
        super().__init__(default)
        self.min = min_val

    def validate(self, value: LessThanT) -> None:
        if value < self.min:
            raise ValidationError(f"Provided value has to be larger than {self.min}")
