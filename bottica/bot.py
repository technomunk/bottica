"""
Discord bot entry point.
Register and run the main logic.
"""

import asyncio
import logging
import random
from typing import Callable, Iterable, List

import discord
from discord.ext import commands as cmd
from discord.ext.commands import Bot as DiscordBot
from discord.mentions import AllowedMentions

from bottica.commands import register_commands
from bottica.infrastructure.error import atask, handle_command_error
from bottica.infrastructure.help import BotticaHelpCommand
from bottica.music.cog import Music
from bottica.response import JEALOUS, REACTIONS
from bottica.sass import make_sass, should_sass
from bottica.version import notify_of_new_changes

# Not my fault discord type-info sucks
# pylint: disable=assigning-non-slot
intents = discord.Intents.all()
intents.typing = False
intents.presences = False
_logger = logging.getLogger(__name__)


class Bottica(DiscordBot):
    def __init__(self, command_prefix, **options):
        super().__init__(command_prefix, help_command=BotticaHelpCommand(), **options)

        self.status_reporters: List[Callable[[cmd.Context], Iterable[str]]] = []
        self.notify = False


bot = Bottica(
    cmd.when_mentioned_or("b.", "B."),
    intents=intents,
    allowed_mentions=AllowedMentions(users=True),
)


@bot.event
async def on_ready():
    _logger.debug("logged in as %s (user id: %d)", bot.user.name, bot.user.id)
    _logger.debug("guilds:")
    for guild in bot.guilds:
        _logger.debug("%s (id: %d)", guild.name, guild.id)

    if bot.notify:
        await notify_of_new_changes(bot.guilds)

    _logger.info("%s is ready", bot.user.name)


@bot.before_invoke
async def pre_invoke(ctx: cmd.Context):
    assert ctx.guild is not None
    _logger.info('calling "%s" in "%s"', ctx.message.content, ctx.guild.name)
    atask(ctx.message.add_reaction(REACTIONS["command_seen"]))  # type: ignore
    if should_sass(ctx):
        atask(ctx.reply(make_sass(ctx)))
    else:
        atask(ctx.typing())


@bot.after_invoke
async def post_invoke(ctx: cmd.Context):
    atask(ctx.message.add_reaction(REACTIONS["command_succeeded"]))  # type: ignore


@bot.listen("on_message")
async def react_to_mentions(message: discord.Message):
    if bot.user not in message.mentions:
        return
    reaction = random.choice(REACTIONS["mention"])
    atask(message.add_reaction(reaction))


@bot.listen("on_message")
async def jealousy(message: discord.Message):
    if message.type != discord.MessageType.new_member or not message.mentions[0].bot:
        return

    reaction = random.choice(REACTIONS["jealousy"])
    atask(message.add_reaction(reaction))
    response = random.choice(JEALOUS)
    atask(message.reply(response))


def run_bot(discord_token: str = "", notify: bool = False) -> None:
    """Run Bottica until cancelled."""
    register_commands(bot)
    asyncio.run(_run_bot(discord_token, notify))


async def _run_bot(discord_token: str, notify: bool):
    async with bot:
        bot.notify = notify
        bot.on_command_error = handle_command_error  # type: ignore
        await bot.add_cog(Music(bot))
        await bot.start(discord_token)
