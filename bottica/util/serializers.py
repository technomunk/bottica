"""Collection of convenient serializers used for data persistence."""

from typing import Any, Callable, Optional, Tuple, TypeAlias, TypeVar

import discord

from bottica.infrastructure.sticky_message import StickyMessage

FromT = TypeVar("FromT")
ToT = TypeVar("ToT")


def discord_voice_client(value: discord.VoiceClient) -> int:
    return value.channel.id


def discord_text_channel(value: discord.TextChannel) -> int:
    return value.id


def sticky_message(value: StickyMessage) -> Tuple[int, int]:
    assert isinstance(value.channel, discord.TextChannel)
    return value.channel.id, value.id


def optional(
    serializer: Callable[[FromT], ToT],
) -> Callable[[Optional[FromT]], Optional[ToT]]:
    def optional_serializer(value: Optional[FromT]) -> Optional[ToT]:
        if value is None:
            return None
        return serializer(value)

    return optional_serializer


DEFAULT_SERIALIZERS: dict[type | TypeAlias, Callable[[Any], Any]] = {
    discord.TextChannel: discord_text_channel,
    Optional[discord.VoiceClient]: optional(discord_voice_client),
    Optional[StickyMessage]: optional(sticky_message),
}
