# Error-handling for the bot

import asyncio
import logging
from asyncio.exceptions import CancelledError
from typing import Coroutine, Optional

import discord.ext.commands as cmd
from discord import Embed
from sentry_sdk import capture_exception

from .friendly_error import make_user_friendly
from response import REACTIONS

_logger = logging.getLogger(__name__)
event_loop = asyncio.get_event_loop()


async def safe_coro(coroutine: Coroutine, ctx: Optional[cmd.Context] = None):
    try:
        await coroutine
    except CancelledError:
        _logger.warning("task was cancelled")
    except cmd.CommandError as error:
        if ctx is not None:
            handle_command_error(ctx, error)
        _logger.exception(error, stacklevel=2)
    except Exception as error:
        capture_exception(error)
        _logger.exception(error, stacklevel=2)
        if ctx is not None:
            # deliberately skip providing ctx to avoid infinite error-handling
            atask(ctx.message.remove_reaction(REACTIONS["command_succeeded"], ctx.me))
            atask(ctx.message.add_reaction(REACTIONS["command_failed"]))
            embed = Embed(
                title=":warning: Internal Error :warning:",
                description="Something went wrong executing the command.",
            )
            atask(ctx.message.reply(embed=embed))


def atask(coroutine: Coroutine, ctx: Optional[cmd.Context] = None):
    """
    Schedule a coroutine to be executed on bot's event loop without awaiting its result.
    """
    event_loop.create_task(safe_coro(coroutine, ctx))


async def handle_command_error(ctx: cmd.Context, error: cmd.CommandError):
    atask(ctx.message.remove_reaction(REACTIONS["command_succeeded"], ctx.me))
    atask(ctx.message.add_reaction(REACTIONS["command_failed"]))

    if not isinstance(error, cmd.UserInputError):
        capture_exception(error)

    response = make_user_friendly(error)
    if not response:
        response = Embed(
            title=":warning: Internal Error :warning:",
            description="Something went wrong executing the command.",
        )

    atask(ctx.message.reply(response))
