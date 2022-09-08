"""Collection of convenient deserializers used for data persistance."""

from typing import Any, Callable, Optional, Tuple, TypeAlias, TypeVar, cast

import discord

from bottica.infrastructure.sticky_message import StickyMessage

FromT = TypeVar("FromT")
ToT = TypeVar("ToT")


async def discord_voice_client(value: int, opts: dict) -> discord.VoiceClient:
    client: discord.Client = opts["client"]
    channel = cast(discord.VoiceChannel, client.get_channel(value))
    return await channel.connect()


def discord_text_channel(value: int, opts: dict) -> discord.TextChannel:
    client: discord.Client = opts["client"]
    return cast(discord.TextChannel, client.get_channel(value))


async def sticky_message(value: Tuple[int, int], opts: dict) -> StickyMessage:
    client: discord.Client = opts["client"]
    channel = cast(discord.TextChannel, client.get_channel(value[0]))
    message = await channel.fetch_message(value[1])
    return StickyMessage(message)


def optional(
    deserializer: Callable[[FromT, dict], ToT],
) -> Callable[[Optional[FromT], dict], Optional[ToT]]:
    def optional_deserializer(value: Optional[FromT], opts: dict) -> Optional[ToT]:
        if value is None:
            return None
        return deserializer(value, opts)

    return optional_deserializer


DEFAULT_DESERIALIZERS: dict[type | TypeAlias, Callable[[Any, dict], Any]] = {
    discord.TextChannel: discord_text_channel,
    Optional[discord.VoiceClient]: optional(discord_voice_client),
    Optional[StickyMessage]: optional(sticky_message),
}
