import discord


def onoff(val: bool) -> str:
    return "on" if val else "off"


def format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    dstr = f"{d}d " if d else ""
    hstr = f"{h}:" if h else ""
    return f"{dstr}{hstr}{m:02d}:{s:02d}"


def contains_real_members(channel: discord.VoiceChannel) -> bool:
    """
    Check whether the provided channel contains non-bot members.
    """
    for member in channel.members:
        if not member.bot:
            return True
    return False
