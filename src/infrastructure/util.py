"""Collection of generic utility functions"""
from inspect import signature
from typing import Any, Tuple, TypeVar

import discord
from discord.ext.commands import Converter

SIZE_NAMES = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
SIZE_INCREMENT = 1 << 10

T = TypeVar("T")


def onoff(val: bool) -> str:
    return "on" if val else "off"


def format_duration(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    dstr = f"{days}d " if days else ""
    hstr = f"{hours}:" if hours else ""
    return f"{dstr}{hstr}{minutes:02d}:{seconds:02d}"


def format_size(bytes_: int) -> str:
    size = float(bytes_)
    for name in SIZE_NAMES:
        if size < SIZE_INCREMENT:
            return f"{size:.1f}{name}"
        size /= SIZE_INCREMENT
    return f"{size:.1f} {SIZE_NAMES[-1]}"


def converted_type_name(converter: Any) -> str:
    annotated_return = ""
    if isinstance(converter, Converter):
        annotated_return = signature(converter.convert).return_annotation
    return annotated_return or converter.__module__.split(".", maxsplit=1)[-1]


def convertee_names(converters: Tuple[Converter]) -> str:
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
