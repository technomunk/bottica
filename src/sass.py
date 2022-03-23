"""Sassy random remarks that give the bot more character."""
from random import choice, random

from discord.ext import commands as cmd

MAX_SASS_CHANCE = 0.25

_SASS_PHASES = [
    "If you insist...",
    "Just for you, bby",
    "^^",
    "Say the magic word!",
    "Why don't you do it yourself?",
]


def _sass_echo(ctx: cmd.Context) -> str:
    return f"{ctx.author.name}.{ctx.invoked_with}"


def _sass_phrase(_ctx: cmd.Context) -> str:
    return choice(_SASS_PHASES)


_ALL_SASS = [
    _sass_echo,
    # Repeat phrase to give it larger weight
    _sass_phrase,
    _sass_phrase,
    _sass_phrase,
    _sass_phrase,
]


def should_sass(ctx: cmd.Context) -> bool:
    """Check whether the author of a command should get sass."""
    weight = len(ctx.author.roles)  # higher ups get more sass
    max_weight = len(ctx.guild.roles)

    sass_chance = MAX_SASS_CHANCE * (weight / max_weight)
    return random() < sass_chance


def make_sass(ctx: cmd.Context) -> str:
    """Generate a sassy response to provided user."""
    chosen_sass = choice(_ALL_SASS)
    return chosen_sass(ctx)
