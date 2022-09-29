"""Utilities for formatting different data types"""

from typing import Iterable


SIZE_NAMES = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
SIZE_INCREMENT = 1 << 10


def onoff(val: bool) -> str:
    return "on" if val else "off"


def duration(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    dstr = f"{days}d " if days else ""
    hstr = f"{hours}:" if hours else ""
    return f"{dstr}{hstr}{minutes:02d}:{seconds:02d}"


def sequence(seq: Iterable[str]) -> str:
    items = list(seq)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    first = ", ".join(items[:-1])
    return f"{first} and {items[-1]}"


def size(bytes_: int) -> str:
    size_ = float(bytes_)
    for name in SIZE_NAMES:
        if size_ < SIZE_INCREMENT:
            return f"{size:.1f}{name}"
        size_ /= SIZE_INCREMENT
    return f"{size_:.1f} {SIZE_NAMES[-1]}"
