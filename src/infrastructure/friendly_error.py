"""Human/user-friendly response wrapping of typical exceptions."""
from typing import Callable, Dict, Type, Union

from discord.ext.commands.errors import (
    BadArgument,
    BadBoolArgument,
    BadColourArgument,
    BadInviteArgument,
    BadUnionArgument,
    BotMissingAnyRole,
    BotMissingPermissions,
    BotMissingRole,
    ChannelNotFound,
    ChannelNotReadable,
    CommandError,
    CommandNotFound,
    CommandOnCooldown,
    DisabledCommand,
    EmojiNotFound,
    GuildNotFound,
    MaxConcurrencyReached,
    MemberNotFound,
    MessageNotFound,
    MissingAnyRole,
    MissingPermissions,
    MissingRequiredArgument,
    MissingRole,
    NSFWChannelRequired,
    RoleNotFound,
    TooManyArguments,
    UserNotFound,
)

from infrastructure.util import convertee_names

CustomMessage = Callable[[CommandError], str]


class FriendlyError(CommandError):
    """An error with a message that can be directly reported to the user."""

    def __init__(self, message: str, *args):
        super().__init__(message, *args)


def human_format(items: list) -> str:
    result = ",".join(str(role) for role in items[:-1])
    return result + f" or {items[-1]}"


def _missing_any_role(error: MissingAnyRole) -> str:
    return "You need to be any of " + human_format(error.missing_roles)


def _bot_missing_any_role(error: BotMissingAnyRole) -> str:
    return "I need to be any of " + human_format(error.missing_roles)


def _missing_permissions(error: MissingPermissions) -> str:
    return f"You need to have {human_format(error.missing_perms)} permissions for that!"


def _bot_missing_permissions(error: BotMissingPermissions) -> str:
    return f"I need to have {human_format(error.missing_perms)} permissions for that!"


def _bad_union_argument(error: BadUnionArgument) -> str:
    return f"Sorry, I need one of {convertee_names(error.converters)}."


UNKNOWN_MENTION = "Who? Sorry, I don't know {error.argument}."


FRIENDLY_MESSAGES: Dict[Type[CommandError], Union[str, CustomMessage]] = {
    # Bad arguments
    BadArgument: "Sorry, I don't understand what you mean. (Bad argument)",
    BadBoolArgument: "Give me `yes` or `no`! COMMIT DAMN IT!",
    BadColourArgument: "Afaik, {error.argument} is not a color.",
    BadInviteArgument: "That invite doesn't look right to me.",
    BadUnionArgument: _bad_union_argument,
    MissingRequiredArgument: "Sorry, I need a {error.param.name}!",
    TooManyArguments: "Whoa whoa whoa, tmi, TMI!",
    # Missing requirements
    BotMissingAnyRole: _bot_missing_any_role,
    BotMissingPermissions: _bot_missing_permissions,
    BotMissingRole: "Sorry, I need to be {error.missing_role} to do that!",
    MissingAnyRole: _missing_any_role,
    MissingPermissions: _missing_permissions,
    MissingRole: "You need to be {error.missing_role} to do that!",
    # Not found
    ChannelNotFound: UNKNOWN_MENTION,
    CommandNotFound: "Sorry, what was that?",
    EmojiNotFound: "What is {error.argument}? Should be an emoji!",
    GuildNotFound: UNKNOWN_MENTION,
    MemberNotFound: UNKNOWN_MENTION,
    MessageNotFound: "Eh. I haven't seen {error.argument}, sorry!",
    RoleNotFound: UNKNOWN_MENTION,
    UserNotFound: UNKNOWN_MENTION,
    # Other
    ChannelNotReadable: "I can't read {error.argument}. :innocent::nerd:",
    CommandOnCooldown: "Wait up, I'm getting overwhelmed. Try in {error.retry_after:.2f} seconds!",
    DisabledCommand: ":swat_smile: hehe, that command is disabled right now :sweat_smile:",
    MaxConcurrencyReached: "I'm really not in the mood right now. Try again later.",
    NSFWChannelRequired: ":hot_pepper: {error.channel} should be NSFW! :hot_pepper:",
}


def make_user_friendly(error: CommandError) -> str:
    if isinstance(error, FriendlyError):
        return error.message

    message = FRIENDLY_MESSAGES.get(type(error), "")
    if isinstance(message, str):
        return message.format(error=error)
    return message(error)
