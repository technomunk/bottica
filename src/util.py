from inspect import signature
from typing import Any, Tuple

from discord.ext.commands import Converter


def onoff(val: bool) -> str:
    return "on" if val else "off"


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    dstr = f"{d}d " if d else ""
    hstr = f"{h}:" if h else ""
    return f"{dstr}{hstr}{m:02d}:{s:02d}"


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
