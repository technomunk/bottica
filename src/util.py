from typing import Tuple


def onoff(val: bool) -> str:
    return "on" if val else "off"


def format_duration(seconds: int) -> str:
    m, s = seconds // 60, seconds % 60
    h, m = m // 60, m % 60
    d, h = h // 24, h % 24
    sections = (d, h, m, s)
    return ":".join(str(el) for el in sections if el)
