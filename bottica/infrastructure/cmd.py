"""Utilities for converting argument sequences into shell-compatible command."""

import shlex
from sys import platform
from typing import Iterable

ArgType = str | int | float


def join(args: Iterable[ArgType]) -> str:
    if platform == "win32":
        return " ".join(escape(arg) for arg in args)
    return shlex.join(escape(arg) for arg in args)


def escape(arg: ArgType) -> str:
    if isinstance(arg, int):
        return str(arg)

    if isinstance(arg, float):
        if round(arg) == arg:
            return format(arg, ".0f")
        return format(arg, "f")

    if isinstance(arg, str) and " " in arg:
        return f'"{arg}"'

    return arg
