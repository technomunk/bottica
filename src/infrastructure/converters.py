"""Data-converters for persistence."""
import enum
import logging
import typing
from typing import Any, Tuple, Type, TypeVar

import discord

from infrastructure.persist import Converter
from infrastructure.sticky_message import StickyMessage as StickyMessageCls

VarT = TypeVar("VarT")
ChannelT = TypeVar("ChannelT", discord.TextChannel, discord.VoiceChannel)
EnumT = TypeVar("EnumT", bound=enum.Enum)
_logger = logging.getLogger(__name__)

# For method parity with parent class we need to match the method signature.
# pylint: disable=unused-argument


class Optional(Converter[typing.Optional[VarT]]):
    def __init__(self, base: Converter[VarT] = Converter()) -> None:
        self.base = base

    def to_serial(self, value: typing.Optional[VarT], **kwargs) -> Any:
        if value is None:
            return None
        return self.base.to_serial(value, **kwargs)

    async def from_serial(self, value: Any, **kwargs) -> typing.Optional[VarT]:
        if value is None:
            return None
        return await self.base.from_serial(value, **kwargs)


class Enum(Converter[EnumT]):
    def __init__(self, enum_type: Type[EnumT]) -> None:
        self.enum_type = enum_type

    def to_serial(self, value: EnumT, **kwargs) -> Any:
        return value.value

    async def from_serial(self, value: Any, **kwargs) -> EnumT:
        return self.enum_type(value)


class DiscordChannel(Converter[ChannelT]):
    def __init__(self, _type_hint: Optional[Type[ChannelT]] = None) -> None:
        pass

    def to_serial(self, value: ChannelT, **kwargs) -> int:
        return value.id

    async def from_serial(self, value: int, **kwargs) -> ChannelT:
        client: discord.Client = kwargs["client"]
        return client.get_channel(value)  # type: ignore


class DiscordVoiceClient(Converter[discord.VoiceClient]):
    def to_serial(self, value: discord.VoiceClient, **kwargs) -> int:
        return value.channel.id  # type: ignore

    async def from_serial(self, value: int, **kwargs) -> discord.VoiceClient:
        client: discord.Client = kwargs["client"]
        channel: discord.VoiceChannel = client.get_channel(value)  # type: ignore
        return await channel.connect()


class StickyMessage(Converter[StickyMessageCls]):
    def to_serial(self, value: StickyMessageCls, **kwargs) -> Tuple[int, int]:
        assert isinstance(value.channel, discord.TextChannel)
        return value.channel.id, value.id

    async def from_serial(self, value: Tuple[int, int], **kwargs) -> StickyMessageCls:
        client: discord.Client = kwargs["client"]
        channel: discord.TextChannel = client.get_channel(value[0])  # type: ignore
        message: discord.Message = await channel.fetch_message(value[1])
        return StickyMessageCls(message)
