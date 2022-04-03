"""
A utility for parsing and interpreting the changelog.

Expects https://keepachangelog.com markdown file format.
"""

from typing import Dict

import discord
from semver import VersionInfo  # type: ignore

from markdown import Markdown

CHANGELOG_FILENAME = "changelog.md"
_INVALID_VERSION = VersionInfo(0)


def parse_latest_version() -> VersionInfo:
    with open(CHANGELOG_FILENAME, "r", encoding="utf8") as changelog_file:
        for line in changelog_file:
            if line.startswith("## "):
                try:
                    clean_line = line.removeprefix("## ").strip()
                    return VersionInfo.parse(clean_line)
                except ValueError:
                    continue

    return _INVALID_VERSION


def parse_changes_since(previous_version: VersionInfo) -> Dict[VersionInfo, Dict[str, str]]:
    with open(CHANGELOG_FILENAME, "r", encoding="utf8") as changelog_file:
        changelog = Markdown.parse(changelog_file)

    changes: Dict[VersionInfo, Dict[str, str]] = {}

    # looks like a false-positive
    # pylint:disable=not-an-iterable
    for section in changelog[0]:
        try:
            version = VersionInfo.parse(section.title)
        except ValueError:
            continue

        if version > previous_version:
            changes[version] = _compose_subsection_dict(section)

    return changes


def compose_changelog_message(changelog: Dict[VersionInfo, Dict[str, str]]) -> discord.Embed:
    """Format changes into neat discord message."""

    embed = discord.Embed(
        title="I have improved!",
        color=discord.Color.dark_purple(),
        url="https://github.com/technomunk/bottica",
    )

    for version in sorted(changelog.keys(), reverse=True):
        changes = changelog[version]
        if sectionless := changes.get(""):
            embed.add_field(name=str(version), value=changes.get("", sectionless))

        first = True
        for title, value in changes.items():
            embed.add_field(name=title, value=value, inline=not first)
            first = False

    return embed


def _compose_subsection_dict(section: Markdown) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if section.content:
        result = {"": section.content}

    for subsection in section:
        result[subsection.title] = subsection.compose_content(include_heading=False)

    return result
