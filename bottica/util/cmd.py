"""Utilities for converting argument sequences into shell-compatible command."""

from subprocess import list2cmdline
from typing import Iterable

ArgType = str | int | float


def join(args: Iterable[ArgType]) -> str:
    return list2cmdline(escape(arg) for arg in args)


def escape(arg: ArgType) -> str:
    if isinstance(arg, int):
        return str(arg)

    if isinstance(arg, float):
        if round(arg) == arg:
            return format(arg, ".0f")
        return format(arg, "f")

    return arg
