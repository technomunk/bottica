"""Bot version definition and related utilities."""

from os import path
from typing import Final, Iterable

import discord
from pepver import Version

from bottica.file import DATA_FOLDER

from .changelog import compose_changelog_message, parse_changes_since, parse_latest_version

BOT_VERSION: Final = parse_latest_version()

_VERSION_FILENAME = path.join(DATA_FOLDER, ".version")


async def notify_of_new_changes(guilds: Iterable[discord.Guild]) -> None:
    version = Version(0)
    if path.exists(_VERSION_FILENAME):
        with open(_VERSION_FILENAME, "r", encoding="utf8") as version_file:
            version = Version.parse(version_file.read())

    if version == BOT_VERSION:
        return

    changelog = parse_changes_since(version)
    if not changelog:
        return

    embed = compose_changelog_message(changelog)
    embed.description = str(BOT_VERSION)

    for guild in guilds:
        if guild.system_channel:
            await guild.system_channel.send(embed=embed)

    with open(_VERSION_FILENAME, "w", encoding="utf8") as version_file:
        version_file.write(str(BOT_VERSION))
