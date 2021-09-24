# Error-handling for the bot

import asyncio
import logging
from asyncio.exceptions import CancelledError
from typing import Coroutine, Optional

from discord import Embed
from discord.ext import commands

from response import REACTIONS
from util import convertee_names

logger = logging.getLogger(__name__)
event_loop = asyncio.get_event_loop()


async def safe_coro(coroutine: Coroutine, ctx: Optional[commands.Context] = None):
    try:
        await coroutine
    except CancelledError:
        logger.warning("task was cancelled")
    except commands.CommandError as error:
        if ctx is not None:
            handle_command_error(ctx, error)
        logger.exception(error, stacklevel=2)
    except Exception as e:
        if ctx is not None:
            # deliberately skip providing ctx to avoid infinite error-handling
            atask(ctx.message.remove_reaction(REACTIONS["command_succeeded"], ctx.me))
            atask(ctx.message.add_reaction(REACTIONS["command_failed"]))
            embed = Embed(
                title=":warning: Internal Error :warning:",
                description="Something went wrong executing the command.",
            )
            atask(ctx.message.reply(embed=embed))
        logger.exception(e, stacklevel=2)


def atask(coroutine: Coroutine, ctx: Optional[commands.Context] = None):
    """
    Schedule a coroutine to be executed on bot's event loop without awaits its result.
    """
    event_loop.create_task(safe_coro(coroutine, ctx))


async def handle_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.UserInputError):
        if isinstance(error, commands.BadUnionArgument):
            param_name = error.errors[0].argument
            reply_text = f"{param_name} is not a {convertee_names(error.converters)}"
            atask(ctx.reply(reply_text))
        atask(ctx.message.remove_reaction(REACTIONS["command_succeeded"]))
        atask(ctx.message.add_reaction(REACTIONS["command_failed"]))
    logger.warning(error)
