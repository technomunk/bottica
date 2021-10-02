import logging

import discord.ext.commands as cmd

from music.error import AuthorNotVoiceConnectedError, BotLacksVoicePermissions

logger = logging.getLogger(__name__)


def author_is_voice_connected(ctx: cmd.Context) -> bool:
    if ctx.author.voice is None:
        raise AuthorNotVoiceConnectedError()
    return True


def bot_has_voice_permission_in_author_channel(ctx: cmd.Context) -> bool:
    if author_is_voice_connected(ctx):
        permissions = ctx.author.voice.channel.permissions_for(ctx.me)
        if not permissions.connect or not permissions.speak:
            raise BotLacksVoicePermissions(ctx.author.voice.channel)
    return False


def bot_is_voice_connected(ctx: cmd.Context) -> bool:
    return ctx.voice_client is not None and ctx.voice_client.is_connected()
