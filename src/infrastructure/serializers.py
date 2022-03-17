import logging
from enum import Enum
from typing import Any, Optional, Tuple, Type, TypeVar

import discord

from infrastructure.error import atask
from infrastructure.persist import Serializer
from infrastructure.sticky_message import StickyMessage

T = TypeVar("T")
EnumT = TypeVar("EnumT", bound=Enum)
ChannelT = TypeVar("ChannelT", bound=discord.abc.GuildChannel)

_logger = logging.getLogger(__name__)


class EnumSerializer(Serializer[EnumT]):
    def __init__(self, enum_type: Type[EnumT]):
        self._type = enum_type

    def to_json(self, variable: EnumT) -> Any:
        return variable.value

    def from_json(self, variable: Any) -> EnumT:
        return self._type(variable)


class OptionalSerializer(Serializer[Optional[T]]):
    def __init__(self, value_serializer: Serializer[T] = Serializer()):
        self.value_serializer = value_serializer

    def finalize(self, **kwargs):
        return self.value_serializer.finalize(**kwargs)

    def to_json(self, variable: Optional[T]) -> Any:
        if variable is None:
            return None
        return self.value_serializer.to_json(variable)

    def from_json(self, variable: Any) -> Optional[T]:
        if variable is None:
            return None
        return self.value_serializer.from_json(variable)


class DiscordChannelSerializer(Serializer[ChannelT]):
    def __init__(self, _type: Type[ChannelT]) -> None:
        self.client: discord.Client = ()

    def finalize(self, **kwargs):
        self.client = kwargs["client"]

    def to_json(self, variable: ChannelT) -> int:
        return variable.id

    def from_json(self, variable: int) -> ChannelT:
        return self.client.get_channel(variable)
