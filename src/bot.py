# Discord bot entry point.
# Register and run the main logic.

import logging
import random
from argparse import ArgumentParser

import discord
import toml
from discord.ext import commands
from discord.ext.commands import Bot as DiscordBot
from discord.mentions import AllowedMentions

from music import MusicCog

BOT_VERSION = "0.2.1"

intents = discord.Intents.default()
bot = DiscordBot(
    "b.",
    intents=intents,
    allowed_mentions=AllowedMentions(users=True),
)
logger = logging.getLogger(__name__)
emojis = {
    "command_heard": "👀",
    "command_failed": "❌",
    "command_succeeded": "✅",
}


@bot.event
async def on_ready():
    logger.debug("logged in as %s (user id: %d)", bot.user.name, bot.user.id)
    logger.debug("guilds:")
    for guild in bot.guilds:
        logger.debug("%s (id: %d)", guild.name, guild.id)
    logger.info("%s is ready", bot.user.name)


@bot.before_invoke
async def pre_invoke(ctx: commands.Context):
    logger.info('calling "%s"', ctx.message.content)
    await ctx.message.add_reaction(emojis["command_heard"])


@bot.after_invoke
async def post_invoke(ctx: commands.Context):
    await ctx.message.add_reaction(
        emojis["command_failed"] if ctx.command_failed else emojis["command_succeeded"]
    )


@bot.command()
async def status(ctx: commands.Context):
    """
    Print the bot status.
    """
    lines = [f"Running version `{BOT_VERSION}`."]
    lines.extend(report() for report in bot.status_reporters)
    embed = discord.Embed(description='\n'.join(lines))
    await ctx.send(embed=embed)


@bot.command()
async def rate(ctx: commands.Context, user: discord.Member):
    """
    Rate the provided user out of 10.
    """
    if user.id == 305440304528359424 or user == bot.user:
        rating = 10
    else:
        rating = random.randint(1, 9)
    await ctx.send(f"{user.mention} is {rating}/10.")


def run_bot():
    # set up arguments
    parser = ArgumentParser(
        prog="bottica", description='Run a discord bot named "Bottica".'
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
    except toml.TomlDecodeError:
        logger.error('Failed to parse "config.toml".')

    if "token" not in config and "token" not in args:
        print("Please provide an API token to use!")
        print('Add it to "config.toml" or provide with --token.')

    # set up logging
    log_level = args.log or config.get("log") or logging.NOTSET
    logging.basicConfig(
        format="%(asctime)s:%(levelname)s:%(name)s:%(funcName)s: %(message)s",
        level=log_level,
    )
    logger.debug("set logging level to %s", log_level)
    logging.getLogger("discord").setLevel("WARNING")

    bot.status_reporters = []
    bot.add_cog(MusicCog(bot))

    # bot.on_command_error = handle_command_error
    bot.run(config["token"])


if __name__ == "__main__":
    run_bot()
