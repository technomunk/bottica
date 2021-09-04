def onoff(val: bool) -> str:
    return "on" if val else "off"


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    sections = (days, hours, minutes, seconds)
    return ":".join(str(el) for el in sections if el)
