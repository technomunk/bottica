from typing import Sequence

import discord
from discord.ext.commands import Context as CmdContext
from discord.ext.commands import MemberConverter, RoleConverter
from discord.ext.commands.errors import MemberNotFound, RoleNotFound

_member_converter = MemberConverter()
_role_converter = RoleConverter()


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


async def get_mentined_members(ctx: CmdContext, mention: str) -> Sequence[discord.Member]:
    """
    Get the sequence of members mentioned.

    If the mention is a role returns all members with such role.
    If the mention is a specific user returns just that user.
    In case of fail returns an empty sequence.
    """
    try:
        role = await _role_converter.convert(ctx, mention)
        return role.members
    except RoleNotFound:
        pass

    try:
        member = await _member_converter.convert(ctx, mention)
        return (member,)
    except MemberNotFound:
        pass

    return ()
