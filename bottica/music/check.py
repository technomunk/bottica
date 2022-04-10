"""Command validity checking."""
import logging

import discord
import discord.ext.commands as cmd

from bottica.music.error import AuthorNotVoiceConnectedError, BotLacksVoicePermissions

_logger = logging.getLogger(__name__)


def author_is_voice_connected(ctx: cmd.Context) -> bool:
    author = ctx.author
    if isinstance(author, discord.User) or author.voice is None:
        raise AuthorNotVoiceConnectedError()
    return True


def bot_has_voice_permission_in_author_channel(ctx: cmd.Context) -> bool:
    if author_is_voice_connected(ctx):
        permissions = ctx.author.voice.channel.permissions_for(ctx.me)  # type: ignore
        if not permissions.connect or not permissions.speak:
            raise BotLacksVoicePermissions(ctx.author.voice.channel)  # type: ignore
        return True
    return False


def bot_is_voice_connected(ctx: cmd.Context) -> bool:
    return (
        ctx.voice_client is not None
        and isinstance(ctx.voice_client, discord.VoiceClient)
        and ctx.voice_client.is_connected()
    )
