"""Standalone commands that don't belong to a particular cog."""

import random
from typing import Set, Union

import discord
from discord.ext import commands as cmd

from bottica.infrastructure.command import command
from bottica.infrastructure.error import atask
from bottica.sass import make_sass
from bottica.version import BOT_VERSION


@command()
async def status(ctx: cmd.Context):
    """Print the bot status."""
    lines = [f"Running version `{BOT_VERSION}`"]
    for reporter in ctx.bot.status_reporters:  # type: ignore
        lines.extend(reporter(ctx))
    embed = discord.Embed(description="\n".join(lines))
    atask(ctx.reply(embed=embed))


@command(descriptions={"user": "the user to rate"})
async def rate(ctx: cmd.Context, user: discord.Member):
    """Rate the provided user out of 10."""
    if user.id == 305440304528359424 or user == ctx.bot.user:
        rating = 10
    elif user.bot:
        rating = 0
    elif user.id == 420481371253768203:
        rating = 9001
    else:
        rating = random.randint(1, 9)
    atask(ctx.reply(f"{user.mention} is {rating}/10."))


@command(descriptions={"maximum": "the maximum possible value of the roll"})
async def roll(
    ctx: cmd.Context,
    maximum: int = 100,
):
    """
    Select a random number up to provided value or 100.
    """
    value = random.randint(1, maximum)
    atask(ctx.reply(f"{value} / {maximum}"))


@command(descriptions={"mentions": "users or roles to chose from"})
async def choose(ctx: cmd.Context, *mentions: Union[discord.Role, discord.Member]):
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


@cmd.command(aliases=["ass"])
async def sass(ctx: cmd.Context):
    """Give me SASS!"""
    atask(ctx.reply(make_sass(ctx)))


def register_commands(bot: cmd.Bot):
    bot.add_command(status)
    bot.add_command(rate)
    bot.add_command(roll)
    bot.add_command(choose)
    bot.add_command(sass)
