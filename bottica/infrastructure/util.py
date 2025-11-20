"""Collection of generic utility functions"""

from inspect import signature
from typing import Any, Tuple, TypeVar

import discord
from discord.ext.commands import Converter

T = TypeVar("T")


def converted_type_name(converter: Any) -> str:
    annotated_return = ""
    if isinstance(converter, Converter):
        annotated_return = signature(converter.convert).return_annotation
    return annotated_return or converter.__module__.split(".", maxsplit=1)[-1]


def convertee_names(converters: Tuple[type, ...]) -> str:
    """
    Generate a human readable version of types of converter results.
    Ex:
    (discord.Role, discord.Member) => "role or member"
    """
    if not converters:
        return ""

    result = ", ".join(converted_type_name(cvtr) for cvtr in converters[:-1])
    if len(converters) >= 2:
        result += " or "
    result += converted_type_name(converters[-1])
    return result


def is_listening(member: discord.Member) -> bool:
    if member.voice is None:
        return False

    return not any([member.voice.afk, member.voice.deaf, member.voice.self_deaf])


def has_listening_members(channel: discord.VoiceChannel) -> bool:
    return any(is_listening(member) for member in channel.members)
