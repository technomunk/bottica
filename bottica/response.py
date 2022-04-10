"""Response messages."""

import random

from discord.ext import commands

SUCCESSES = (
    "Success",
    "Done",
    ":100:",
    ":ok:",
    ":smile::+1:",
)

FAILS = (
    "Fail",
    "Bump",
    "Poop",
    ":poop:",
    ":frowning::-1:",
)

JEALOUS = (
    "Who's this?",
    "Who is that?",
    "What are they doing here?",
    "Are you cheating on me?",
    "But what am I to you?",
)

REACTIONS = {
    "command_seen": "👀",
    "command_failed": "❌",
    "command_succeeded": "✅",
    "mention": ["💋", "👧", "🤖", "🕵️‍♀️", "👩‍💻", "🤹‍♀️"],
    "jealousy": ["🌭", "🕵️‍♀️", "🤡", "💩", "💢"],
}

DEFAULT_TIMEOUT = 10


async def random_fail(ctx: commands.Context):
    return await ctx.reply(random.choice(FAILS), delete_after=DEFAULT_TIMEOUT)


async def random_success(ctx: commands.Context):
    return await ctx.reply(random.choice(SUCCESSES), delete_after=DEFAULT_TIMEOUT)
