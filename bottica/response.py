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
    "command_seen": "๐",
    "command_failed": "โ",
    "command_succeeded": "โ",
    "mention": ["๐", "๐ง", "๐ค", "๐ต๏ธโโ๏ธ", "๐ฉโ๐ป", "๐คนโโ๏ธ"],
    "jealousy": ["๐ญ", "๐ต๏ธโโ๏ธ", "๐คก", "๐ฉ", "๐ข"],
}

DEFAULT_TIMEOUT = 10


async def random_fail(ctx: commands.Context):
    return await ctx.reply(random.choice(FAILS), delete_after=DEFAULT_TIMEOUT)


async def random_success(ctx: commands.Context):
    return await ctx.reply(random.choice(SUCCESSES), delete_after=DEFAULT_TIMEOUT)
