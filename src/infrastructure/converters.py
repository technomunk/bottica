import logging
from abc import ABC
from functools import partial
from inspect import isawaitable
from lib2to3.pgen2.token import OP
from typing import Any, Callable, Dict, Literal, Optional, Tuple, Type, TypeVar, overload

import discord

from infrastructure.sticky_message import StickyMessage

T = TypeVar("T")
_logger = logging.getLogger(__name__)


class _HasId(ABC):
    id: int


class _HasTextChannel(ABC):
    text_channel: discord.TextChannel


def get_id(has_id: _HasId) -> int:
    return has_id.id


def get_voice_client_id(voice_client: discord.VoiceClient) -> int:
    return voice_client.channel.id


def identity(value: T) -> T:
    return value


SAVE_CONVERTERS: Dict[Type, Callable[[Any], Any]] = {
    discord.TextChannel: get_id,
    discord.VoiceClient: get_voice_client_id,
    StickyMessage: get_id,
}


def load_converters(
    client: discord.Client,
    has_text_channel: _HasTextChannel,
) -> Dict[Type | object, Callable[[Any], Any]]:
    return {
        discord.TextChannel: partial(discord.Client.get_channel, client),
        Optional[discord.VoiceClient]: partial(_fetch_voice_client, client),
        Optional[StickyMessage]: partial(_fetch_sticky_message, has_text_channel),
    }


async def _fetch_voice_client(
    client: discord.Client, id: Optional[int]
) -> Optional[discord.VoiceClient]:
    channel: Optional[discord.VoiceChannel] = client.get_channel(id)
    if channel is None:
        return None
    return await channel.connect()


async def _fetch_sticky_message(
    has_text_channel: _HasTextChannel,
    id: Optional[int],
) -> Optional[StickyMessage]:
    if id is None:
        return None
    message: Optional[discord.Message] = await has_text_channel.text_channel.fetch_message(id)
    if message is None:
        return None
    return StickyMessage(message)
