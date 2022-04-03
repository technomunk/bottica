"""New version release utility."""

import os
import re
import subprocess
import sys
from functools import partial
from typing import Tuple

import click
from semver import VersionInfo  # type: ignore

from markdown import Markdown
from version import BOT_VERSION

VERSION_BUMPS = {
    "major": partial(BOT_VERSION.bump_major),
    "minor": partial(BOT_VERSION.bump_minor),
    "patch": partial(BOT_VERSION.bump_patch),
}


@click.command()
@click.argument(
    "bump",
    type=click.Choice(["major", "minor", "patch"], case_sensitive=False),
    required=False,
    default="patch",
)
@click.option(
    "--dry-run", is_flag=True, help="Avoid changing the actual files or creating the release."
)
def release(bump: str, dry_run: bool) -> None:
    """
    Release a new version of the bot.

    Requires "git" and "gh" cli commands to be installed on the system.
    The release process consists of:
    * Updating changelog.md file by moving [Unreleased] section to the new version section.
    * Updates pyproject.toml version.
    * Makes sure the current branch is the default one.
    * Makes a git commit with the changes above.
    * Tags the new commit with v<version> tag.
    * Pushes the commit and the tag upstream.
    * Makes a new GitHub release with the latest changelog entry as the changes section.
    """
    if bump not in VERSION_BUMPS:
        sys.exit(f"bump must be one of {VERSION_BUMPS.keys()}")

    _ensure_dependencies_exist()
    _ensure_latest_trunk_branch()

    _print_commits_since_last_version()

    version = click.prompt(
        "Release version",
        default=str(VERSION_BUMPS[bump]()),
        value_proc=partial(VersionInfo.parse),
    )

    changes, updated_changelog = _prepare_changelog(version)

    if changes:
        click.echo("Changelog:")
        click.echo(changes)
    else:
        click.confirm("Continue without changelog update?", default=False, abort=True)

    click.confirm("Proceed with release?", default=True, abort=True)

    _update_files(version, updated_changelog)

    if not dry_run:
        subprocess.run(["git", "add", "pyproject.toml", "changelog.md"], check=True)
        subprocess.run(["git", "commit", "-m", f"Bump to version {version}", "-n"], check=True)
        subprocess.run(["git", "tag", "-a", f"v{version}", "-m", str(version)], check=True)
        subprocess.run(["git", "push", "--follow-tags"], check=True)

        subprocess.run(
            ["gh", "release", "create", f"v{version}", "-t", str(version), "-F", "-"],
            text=True,
            input=changes.replace("## ", "# "),
            check=False,
        )
    click.echo("done")


def _ensure_dependencies_exist() -> None:
    """Raise errors if the required cli tools are not available."""
    subprocess.run(["git", "--version"], check=True)
    subprocess.run(["gh", "--version"], check=True)


def _get_default_branch_name() -> str:
    git_remote = subprocess.run(
        ["git", "remote", "show", "origin"],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"HEAD branch: (?P<branch>.+)\n", git_remote.stdout)
    if match:
        return match.group("branch")

    raise RuntimeError("Could not determine head branch name")


def _ensure_latest_trunk_branch() -> None:
    default_branch = _get_default_branch_name()
    git_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    )
    if git_branch.stdout.strip() != default_branch:
        sys.exit(f"please switch to {default_branch} branch")
    subprocess.run(["git", "pull", "--ff-only"], check=True)


def _print_commits_since_last_version() -> None:
    click.echo(f"Commits since {BOT_VERSION}:")
    subprocess.run(["git", "log", f"v{BOT_VERSION}..@", "--oneline"], check=False)


def _prepare_changelog(version: VersionInfo) -> Tuple[str, Markdown]:
    changelog = Markdown.parse_file("changelog.md")
    for index, subsection in enumerate(changelog[0]):
        if "unreleased" in subsection.title.lower():
            if not subsection:
                # Avoid populating a new entry
                return "", changelog

            changelog[0].subsections.insert(index, Markdown(2, subsection.title))
            subsection.title = str(version)
            return subsection.compose_content(), changelog

    return "", changelog


def _update_files(version: VersionInfo, changelog: Markdown) -> None:
    with (
        open("pyproject.toml", "r", encoding="utf8") as rfile,
        open("pyproject.new.toml", "w", encoding="utf8") as wfile,
    ):
        section = ""

        for line in rfile:
            if section_match := re.fullmatch(r"\[(?P<section>[\w\.]+)\]", line.strip()):
                section = section_match.group("section")

            is_version_line = re.fullmatch(r'version\s*=\s*"\d+\.\d+\.\d+"', line.strip())
            if is_version_line and section == "tool.poetry":
                wfile.write(f'version = "{version}"\n')
                continue

            wfile.write(line)

    os.replace("pyproject.new.toml", "pyproject.toml")

    with open("changelog.md", "w", encoding="utf8") as changelog_file:
        changelog.compose_content(changelog_file)
