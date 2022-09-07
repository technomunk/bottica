"""
Bottica data management tooling.
Use caution when using while Bottica is running.
"""

import csv
import logging
import logging.handlers
import sys
from dataclasses import asdict, astuple
from os import listdir, remove, replace, stat
from os.path import isfile, join
from typing import Callable, List, Set, Tuple

import click
import sentry_sdk
import toml

from bottica.bot import run_bot
from bottica.file import AUDIO_FOLDER, GUILD_SET_FOLDER, SONG_REGISTRY_FILENAME
from bottica.infrastructure.util import format_size
from bottica.music.song import FILE_ENCODING, SongCSVDialect, SongKey, open_song_registry
from bottica.release import release
from bottica.version import BOT_VERSION
from bottica.version.migrate import MIGRATIONS

_logger = logging.getLogger(__name__)

MULTIPLIERS = {
    "K": 1 << 10,
    "M": 1 << 20,
    "G": 1 << 30,
}


@click.group()
def cli() -> int:
    """Bottica management CLI."""
    return 0


@cli.command()
@click.argument("count", type=int)
@click.argument(
    "unit",
    type=str,
    required=False,
    default="",
    shell_complete=lambda *_: MULTIPLIERS.keys(),
)
def prune(count: int, unit: str) -> None:
    """Unlink and remove files larger than provided size."""
    if count < 1:
        click.echo("Size must be positive!")
        return

    multiplier = MULTIPLIERS.get(unit, 1)
    min_size = count * multiplier

    songs_to_unlink, files_to_remove, bytes_removed = _gather_songs_larger_than(min_size)

    if not songs_to_unlink:
        click.echo(f"Found no files larger than {count}{unit}. Exiting.")
        return

    click.echo(f"Found {len(songs_to_unlink)} files larger than {count}{unit}:")
    for filename in files_to_remove:
        click.echo(filename)
    remove_files = click.confirm(f"Totalling {format_size(bytes_removed)}. Delete them?")

    if remove_files:

        def unlink_predicate(key: SongKey) -> bool:
            return key in songs_to_unlink

        for filename in listdir(GUILD_SET_FOLDER):
            _unlink_songs_in(join(GUILD_SET_FOLDER, filename), unlink_predicate)
        _unlink_songs_in(SONG_REGISTRY_FILENAME, unlink_predicate)
        for filename in files_to_remove:
            remove(join(AUDIO_FOLDER, filename))
        click.echo(f"Removed {format_size(bytes_removed)}. Have a good day!")
    else:
        click.echo("Operation aborted, all files remain.")


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print cleaned entries.")
def clean(verbose: bool) -> None:
    """Remove any data not linked to Bottica."""
    tmp_filepath = SONG_REGISTRY_FILENAME + ".temp"
    linked_filenames = set()
    known_songs = set()
    with (
        open(tmp_filepath, "w", encoding=FILE_ENCODING) as wfile,
        open_song_registry(SONG_REGISTRY_FILENAME) as song_registry,
    ):
        writer = csv.writer(wfile, dialect=SongCSVDialect)
        header_written = False
        for song_info in song_registry:
            if isfile(join(AUDIO_FOLDER, song_info.filename)):
                linked_filenames.add(song_info.filename)
                known_songs.add(song_info.key)
                if not header_written:
                    writer.writerow(asdict(song_info).keys())
                    header_written = True
                writer.writerow(astuple(song_info))
            elif verbose:
                click.echo(f"Unlinked {song_info.key} as no file is found.")

    replace(tmp_filepath, SONG_REGISTRY_FILENAME)

    for filename in listdir(AUDIO_FOLDER):
        if filename not in linked_filenames:
            remove(join(AUDIO_FOLDER, filename))
            if verbose:
                click.echo(f"Removed {filename} as it's not linked.")

    for filename in listdir(GUILD_SET_FOLDER):
        _unlink_songs_in(
            join(GUILD_SET_FOLDER, filename),
            lambda key: key not in known_songs,
            verbose,
        )


@cli.command()
@click.argument("version", type=click.Choice(list(MIGRATIONS.keys())))
@click.option("--keep-files", is_flag=True, help="Keep old files for extra safety.")
def migrate(version: str, keep_files: bool) -> None:
    migration_procedure = MIGRATIONS.get(version)
    if not migration_procedure:
        click.echo(f"Unknown migration version. Must be one of {MIGRATIONS.keys()}")
        return

    files_to_remove = migration_procedure()
    if not keep_files:
        for filename in files_to_remove:
            remove(filename)

    click.echo(f"Migration {version} => {BOT_VERSION} complete")


@cli.command()
@click.option(
    "--discord-token",
    type=str,
    help="Discord API token to use, will override one provided in config.",
)
@click.option(
    "--sentry-token",
    type=str,
    help="Sentry SDK API token to use. Will override one provided in config. (optional)",
)
@click.option(
    "--log",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    help="Set the logging level.",
)
@click.option("--notify", is_flag=True, help="Notify users of any changes.")
def run(discord_token: str, sentry_token: str, log: str, notify: bool) -> None:
    """Run the bot until cancelled."""
    config = {}
    try:
        config = toml.load("config.toml")
    except toml.TomlDecodeError as e:
        _logger.error('Failed to parse "config.toml".')
        _logger.exception(e, stack_info=False)

    if not any([discord_token, config.get("discord_token")]):
        click.echo("Please provide a Discord API token to use!")
        click.echo('Add it to "config.toml" or provide with --discord-token.')
        return

    sentry_token = sentry_token or config.get("sentry_token", "")
    if sentry_token:
        click.echo("Initializing sentry")
        # Probably sentry SDK issue
        # pylint: disable=abstract-class-instantiated
        sentry_sdk.init(sentry_token)

    # set up logging
    log_level = log or config.get("log") or logging.INFO
    click.echo(f"set logging level to {log_level}")
    logging.basicConfig(
        format="%(asctime)s:%(levelname)s:%(name)s:%(funcName)s: %(message)s",
        level=log_level,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "bottica-run.log",
                encoding="utf8",
                maxBytes=2**20,
                backupCount=16,
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("discord").setLevel(logging.WARNING)

    run_bot(discord_token or config["discord_token"], notify)


def _gather_songs_larger_than(min_size: int) -> Tuple[Set[SongKey], List[str], int]:
    """
    Gather filenames linked via song registry for files that are more than provided byte count.

    Returns set of song keys that should be removed, list of files that are
    associated with provided songs and the total file size.
    """
    songs_to_remove = set()
    files_to_remove = []
    bytes_removed = 0
    with open_song_registry(SONG_REGISTRY_FILENAME) as song_registry:
        for song_info in song_registry:
            filepath = join(AUDIO_FOLDER, song_info.filename)
            file_size = stat(filepath).st_size
            if file_size >= min_size:
                songs_to_remove.add(song_info.key)
                files_to_remove.append(song_info.filename)
                bytes_removed += file_size

    return songs_to_remove, files_to_remove, bytes_removed


def _unlink_songs_in(filepath: str, predicate: Callable[[SongKey], bool], verbose: bool = False):
    tmp_filename = filepath + ".temp"
    with (
        open(filepath, "r", encoding=FILE_ENCODING) as rfile,
        open(tmp_filename, "w", encoding=FILE_ENCODING) as wfile,
    ):
        reader = csv.reader(rfile, dialect=SongCSVDialect)
        try:
            header_row = next(reader)
        except StopIteration:
            header_row = ["domain", "id"]

        assert list(header_row[:2]) == ["domain", "id"], "Unable to unlink non-csv files"

        writer = csv.writer(wfile, dialect=SongCSVDialect)
        writer.writerow(header_row)

        for row in reader:
            key = row[0], row[1]
            if predicate(key):
                # unlinking happens by not writing the line to the new file
                if verbose:
                    click.echo(f"Unlinked {key} from {filepath}.")
            else:
                writer.writerow(row)

    replace(tmp_filename, filepath)


if __name__ == "__main__":
    cli.add_command(release)
    cli()
