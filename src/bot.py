# Discord bot entry point.
# Register and run the main logic.

import logging
import random
from argparse import ArgumentParser
from typing import Set, Union

import discord
import toml
from discord.ext import commands
from discord.ext.commands import Bot as DiscordBot
from discord.mentions import AllowedMentions

from error import atask, event_loop, handle_command_error
from music.cog import MusicCog
from response import REACTIONS

BOT_VERSION = "0.11.2"

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.members = True
bot = DiscordBot(
    "b.",
    loop=event_loop,
    intents=intents,
    allowed_mentions=AllowedMentions(users=True),
)
logger = logging.getLogger(__name__)


@bot.event
async def on_ready():
    logger.debug("logged in as %s (user id: %d)", bot.user.name, bot.user.id)
    logger.debug("guilds:")
    for guild in bot.guilds:
        logger.debug("%s (id: %d)", guild.name, guild.id)
    logger.info("%s is ready", bot.user.name)


@bot.before_invoke
async def pre_invoke(ctx: commands.Context):
    logger.info('calling "%s" in "%s"', ctx.message.content, ctx.guild.name)
    atask(ctx.message.add_reaction(REACTIONS["command_seen"]))
    atask(ctx.trigger_typing())


@bot.after_invoke
async def post_invoke(ctx: commands.Context):
    atask(ctx.message.add_reaction(REACTIONS["command_succeeded"]))


@bot.command()
async def status(ctx: commands.Context):
    """Print the bot status."""
    lines = [
        f"Running version `{BOT_VERSION}`",
        "How do you do, fellow humans?",
    ]
    for reporter in bot.status_reporters:
        lines.extend(reporter(ctx))
    embed = discord.Embed(description="\n".join(lines))
    atask(ctx.reply(embed=embed))


@bot.command()
async def rate(ctx: commands.Context, user: discord.Member):
    """Rate the provided user out of 10."""
    if user.id == 305440304528359424 or user == bot.user:
        rating = 10
    elif user.id == 420481371253768203:
        rating = 9001
    else:
        rating = random.randint(1, 9)
    atask(ctx.reply(f"{user.mention} is {rating}/10."))


@bot.command()
async def roll(ctx: commands.Context, max: int = 100):
    """Select a random number up to provided value or 100."""
    value = random.randint(1, max)
    atask(ctx.reply(f"{value} / {max}"))


@bot.command()
async def choose(ctx: commands.Context, *mentions: Union[discord.Role, discord.Member]):
    """Select a single member from provided mentions."""
    selection_set: Set[discord.Member] = set()
    for mention in mentions:
        if isinstance(mention, discord.Role):
            for member in mention.members:
                selection_set.add(member)
        elif isinstance(mention, discord.Member):
            selection_set.add(mention)
        else:
            raise TypeError
    reply_content = (
        random.choice(tuple(selection_set)).mention if selection_set else "Nobody to choose!"
    )
    atask(ctx.reply(reply_content))


def run_bot():
    # set up arguments
    parser = ArgumentParser(
        prog="bottica",
        description='Run a discord bot named "Bottica".',
    )
    parser.add_argument(
        "--token",
        type=str,
        help="Discord API token to use, will override one provided in config.",
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
        logger.error('Failed to parse "config.toml".')
        logger.exception(e, stack_info=False)

    if "token" not in config and not args.token:
        print("Please provide an API token to use!")
        print('Add it to "config.toml" or provide with --token.')
        return

    # set up logging
    log_level = args.log or config.get("log") or logging.INFO
    logger.debug("set logging level to %s", log_level)
    logging.basicConfig(
        format="%(asctime)s:%(levelname)s:%(name)s:%(funcName)s: %(message)s",
        level=log_level,
    )
    logging.getLogger("discord").setLevel(logging.WARNING)

    bot.status_reporters = []
    bot.add_cog(MusicCog(bot))

    bot.on_command_error = handle_command_error
    bot.run(args.token or config["token"])


if __name__ == "__main__":
    run_bot()
