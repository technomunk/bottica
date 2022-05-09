"""Decorators for filtering command contexts."""

from discord.ext import commands as cmd

from .friendly_error import FriendlyError


async def has_guild(ctx: cmd.Context) -> bool:
    if ctx.guild is None:
        raise FriendlyError("Sorry, you'll need to say that in a server. :blush:")
    return True


guild_only = cmd.check(has_guild)
