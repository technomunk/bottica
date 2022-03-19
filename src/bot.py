# Discord bot entry point.
# Register and run the main logic.

import logging
import random
from argparse import ArgumentParser

import discord
import sentry_sdk
import toml
from discord.ext import commands as cmd
from discord.ext.commands import Bot as DiscordBot
from discord.mentions import AllowedMentions

from commands import register_commands
from infrastructure.error import atask, event_loop, handle_command_error
from music.cog import Music
from response import JEALOUS, REACTIONS
from sass import make_sass, should_sass

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.members = True
_logger = logging.getLogger(__name__)


class Bottica(DiscordBot):
    async def close(self) -> None:
        for cog in self.cogs.values():
            if closer := getattr(cog, "close"):
                await closer()
        await super().close()


bot = Bottica(
    cmd.when_mentioned_or("b."),
    loop=event_loop,
    intents=intents,
    allowed_mentions=AllowedMentions(users=True),
)


@bot.event
async def on_ready():
    _logger.debug("logged in as %s (user id: %d)", bot.user.name, bot.user.id)
    _logger.debug("guilds:")
    for guild in bot.guilds:
        _logger.debug("%s (id: %d)", guild.name, guild.id)
    _logger.info("%s is ready", bot.user.name)


@bot.before_invoke
async def pre_invoke(ctx: cmd.Context):
    _logger.info('calling "%s" in "%s"', ctx.message.content, ctx.guild.name)
    atask(ctx.message.add_reaction(REACTIONS["command_seen"]))
    if should_sass(ctx):
        atask(ctx.reply(make_sass(ctx)))
    else:
        atask(ctx.trigger_typing())


@bot.after_invoke
async def post_invoke(ctx: cmd.Context):
    atask(ctx.message.add_reaction(REACTIONS["command_succeeded"]))


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


def run_bot():
    # set up arguments
    parser = ArgumentParser(
        prog="bottica",
        description='Run a discord bot named "Bottica".',
    )
    parser.add_argument(
        "--discord-token",
        type=str,
        help="Discord API token to use, will override one provided in config.",
    )
    parser.add_argument(
        "--sentry-token",
        type=str,
        help="Sentry SDK API token to use. Will override one provided in config. (optional)",
    )
    parser.add_argument(
        "--log",
        choices=(
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ),
    )

    args = parser.parse_args()

    # parse configs
    config = {}
    try:
        config = toml.load("config.toml")
    except toml.TomlDecodeError as e:
        _logger.error('Failed to parse "config.toml".')
        _logger.exception(e, stack_info=False)

    if "discord_token" not in config and not args.discor_token:
        print("Please provide a Discord API token to use!")
        print('Add it to "config.toml" or provide with --discord-token.')
        return

    sentry_token = args.sentry_token or config.get("sentry_token", "")
    if sentry_token:
        print("Initializing sentry")
        sentry_sdk.init(sentry_token)

    # set up logging
    log_level = args.log or config.get("log") or logging.INFO
    print("set logging level to", log_level)
    logging.basicConfig(
        format="%(asctime)s:%(levelname)s:%(name)s:%(funcName)s: %(message)s",
        level=log_level,
    )
    logging.getLogger("discord").setLevel(logging.WARNING)

    bot.status_reporters = []
    register_commands(bot)
    bot.add_cog(Music(bot))

    bot.on_command_error = handle_command_error
    bot.run(args.discord_token or config["discord_token"])


if __name__ == "__main__":
    run_bot()
