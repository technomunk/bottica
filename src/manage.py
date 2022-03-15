"""
Bottica data management tooling.
Use caution when using while Bottica is running.
"""

import csv
from dataclasses import asdict, astuple
from os import listdir, remove, replace, stat
from os.path import isfile, splitext
from typing import Callable, List, Set, Tuple

import click
from ffmpeg_normalize import FFmpegNormalize

from infrastructure.util import format_size
from music.file import AUDIO_FOLDER, GUILD_SET_FOLDER, SONG_REGISTRY_FILENAME
from music.normalize import normalize_song
from music.song import FILE_ENCODING, SongCSVDialect, SongKey, open_song_registry
from version import BOT_VERSION
from version.migrate import MIGRATIONS

MULTIPLIERS = {
    "K": 1 << 10,
    "M": 1 << 20,
    "G": 1 << 30,
}


@click.group()
def cli():
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
def prune(count: int, unit: str):
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

        for filepath in listdir(GUILD_SET_FOLDER):
            _unlink_songs_in(GUILD_SET_FOLDER + filepath, unlink_predicate)
        _unlink_songs_in(SONG_REGISTRY_FILENAME, unlink_predicate)
        for filename in files_to_remove:
            remove(AUDIO_FOLDER + filename)
        click.echo(f"Removed {format_size(bytes_removed)}. Have a good day!")
    else:
        click.echo("Operation aborted, all files remain.")


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print cleaned entries.")
def clean(verbose: bool):
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
            if isfile(AUDIO_FOLDER + song_info.filename):
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
            remove(AUDIO_FOLDER + filename)
            if verbose:
                click.echo(f"Removed {filename} as it's not linked.")

    for filepath in listdir(GUILD_SET_FOLDER):
        _unlink_songs_in(
            GUILD_SET_FOLDER + filepath,
            lambda key: key not in known_songs,
            verbose,
        )


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Print normalized entries.")
@click.option("--keep-file", is_flag=True, help="Keep existing files on disk.")
@click.option("-f", "--force", is_flag=True, help="Forcefully override all files (opus included).")
def normalize(verbose: bool, keep_file: bool, force: bool):
    """Loudness-normalize all songs in the audio folder."""
    normalization_config = FFmpegNormalize(
        target_level=-18,
        print_stats=verbose,
        debug=verbose,
        audio_codec="libopus",
        video_disable=True,
        subtitle_disable=True,
        metadata_disable=True,
        chapters_disable=True,
        output_format="opus",
    )

    registry_filename, _ = splitext(SONG_REGISTRY_FILENAME)
    new_registry_filename = registry_filename + "_norm.csv"
    with (
        open_song_registry(SONG_REGISTRY_FILENAME) as song_registry,
        open(new_registry_filename, "w", encoding=FILE_ENCODING) as new_song_file,
    ):
        writer = csv.writer(new_song_file, dialect=SongCSVDialect)
        header_written = False
        for song_info in song_registry:
            try:
                if song_info.ext != normalization_config.output_format or force:
                    normalize_song(song_info, normalization_config, keep_file)
            except Exception as e:
                print(e)

            if not header_written:
                writer.writerow(asdict(song_info).keys())

            writer.writerow(astuple(song_info))

    if not keep_file:
        replace(new_registry_filename, SONG_REGISTRY_FILENAME)


@cli.command()
@click.argument(
    "version",
    type=str,
    shell_complete=lambda *_: MIGRATIONS.keys(),
)
@click.option("--keep-files", is_flag=True, help="Keep old files for extra safety.")
def migrate(version: str, keep_files: bool):
    migration_procedure = MIGRATIONS.get(version)
    if not migration_procedure:
        print("Unknown migration version. Must be one of ", MIGRATIONS.keys())
        return

    files_to_remove = migration_procedure()
    if not keep_files:
        for filename in files_to_remove:
            remove(filename)

    print("Migration", version, "=>", BOT_VERSION, "complete")


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
            filepath = AUDIO_FOLDER + song_info.filename
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
        header_row = next(reader)

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
    cli()
