"""Error-handling for the bot."""

import asyncio
import logging
from asyncio.exceptions import CancelledError
from typing import Coroutine, Optional

import discord.ext.commands as cmd
from discord import Embed
from sentry_sdk import capture_exception

from response import REACTIONS

from .friendly_error import make_user_friendly

_logger = logging.getLogger(__name__)
event_loop = asyncio.get_event_loop()


async def safe_coro(coroutine: Coroutine, ctx: Optional[cmd.Context] = None):
    # We definitely want to catch all non-exit errors for sentry and robustness
    # pylint: disable=broad-except
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
            success_reaction: str = REACTIONS["command_succeeded"]  # type: ignore
            failed_reaction: str = REACTIONS["command_failed"]  # type: ignore
            atask(ctx.message.remove_reaction(success_reaction, ctx.me))
            atask(ctx.message.add_reaction(failed_reaction))
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
    _logger.exception(error, stacklevel=2)
    atask(ctx.message.remove_reaction(REACTIONS["command_succeeded"], ctx.me))  # type: ignore
    atask(ctx.message.add_reaction(REACTIONS["command_failed"]))  # type: ignore

    if not isinstance(error, cmd.UserInputError):
        capture_exception(error)

    response = make_user_friendly(error)
    if response:
        atask(ctx.message.reply(response))
        return

    fancy_response = Embed(
        title=":warning: Internal Error :warning:",
        description="Something went wrong executing the command.",
    )
    atask(ctx.message.reply(embed=fancy_response))
