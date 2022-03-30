"""
A utility for parsing and interpreting the changelog.

Expects https://keepachangelog.com markdown file format.
"""

from io import StringIO
from typing import Dict, List

import discord
from semver import VersionInfo  # type: ignore

CHANGELOG_FILENAME = "changelog.md"
_INVALID_VERSION = VersionInfo(0)


def parse_changes_since(version: VersionInfo = VersionInfo(0)) -> Dict[VersionInfo, Dict[str, str]]:
    """Parse changes since provided version."""

    changelog: Dict[VersionInfo, Dict[str, str]] = {}
    changelog_started = False

    with open(CHANGELOG_FILENAME, "r", encoding="utf8") as changelog_file:
        section_version = _INVALID_VERSION
        changes: Dict[str, str] = {}
        section_title = ""
        section_content = StringIO()

        for line in changelog_file:
            if line.startswith("## "):
                if changes:
                    changelog[section_version] = changes
                    changes = {}

                try:
                    section_version = VersionInfo.parse(line.removeprefix("## ").strip())
                    changelog_started = True
                    if section_version <= version:
                        return changelog
                except ValueError:
                    pass  # not an interesting section

                continue

            if not changelog_started:
                continue

            if line.startswith("###"):
                section_text = section_content.getvalue()
                if section_title or section_text:
                    changes[section_title] = section_text
                section_title = line.removeprefix("###").strip()
                section_content = StringIO()
                continue

            if section_version != _INVALID_VERSION:
                if line := line.strip():
                    section_content.write(line)
                    section_content.write("\n")

        section_text = section_content.getvalue()
        if section_title or section_text:
            changes[section_title] = section_text

        changelog[section_version] = changes

    return changelog


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


def _format_change_section(lines: List[str]) -> str:
    add_padding = False
    text = StringIO()

    for line in lines:
        if line.startswith("#") and add_padding:
            text.write("\n")  # add a little bit of padding

        if line:
            text.write(line)
            text.write("\n")
            add_padding = True

    return text.getvalue()
