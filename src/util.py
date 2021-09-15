import discord


def onoff(val: bool) -> str:
    return "on" if val else "off"


def format_duration(seconds: int) -> str:
    m, s = seconds // 60, seconds % 60
    h, m = m // 60, m % 60
    d, h = h // 24, h % 24
    sections = (d, h, m, s)
    return ":".join(format(el, "02d") for el in sections if el)


def contains_real_members(channel: discord.VoiceChannel) -> bool:
    '''
    Check whether the provided channel contains non-bot members.
    '''
    for member in channel.members:
        if not member.bot:
            return True
    return False
