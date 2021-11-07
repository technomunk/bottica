# Bottica data management tooling.
# Use caution when using while Bottica is running.

from os import listdir, remove, replace, stat
from os.path import isfile
from typing import Callable, List, Set, Tuple, cast

import click

from music.file import AUDIO_FOLDER, GUILD_SET_FOLDER, SONG_REGISTRY_FILENAME
from music.song import SongInfo, SongKey
from util import format_size

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
@click.argument("unit", type=str, required=False, default="")
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
    with open(tmp_filepath, "w", encoding="utf8") as wfile:
        with open(SONG_REGISTRY_FILENAME, "r", encoding="utf8") as rfile:
            for line in rfile:
                song_info = SongInfo.from_line(line)
                if isfile(AUDIO_FOLDER + song_info.filename):
                    linked_filenames.add(song_info.filename)
                    known_songs.add(song_info.key)
                    wfile.write(line)
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


def _gather_songs_larger_than(min_size: int) -> Tuple[Set[SongKey], List[str], int]:
    """
    Gather filenames linked via song registry for files that are more than provided byte count.

    Returns set of song keys that should be removed,
    list of files that are associated with provided songs
    and the total file size.
    """
    songs_to_remove = set()
    files_to_remove = []
    bytes_removed = 0
    with open(SONG_REGISTRY_FILENAME, "r", encoding="utf8") as file:
        for line in file:
            song_info = SongInfo.from_line(line)
            filepath = AUDIO_FOLDER + song_info.filename
            file_size = stat(filepath).st_size
            if file_size >= min_size:
                songs_to_remove.add(song_info.key)
                files_to_remove.append(song_info.filename)
                bytes_removed += file_size

    return songs_to_remove, files_to_remove, bytes_removed


def _unlink_songs_in(filepath: str, predicate: Callable[[SongKey], bool], verbose: bool = False):
    tmp_filename = filepath + ".temp"
    with open(tmp_filename, "w", encoding="utf8") as wfile:
        with open(filepath, "r", encoding="utf8") as rfile:
            for line in rfile:
                key = cast(SongKey, tuple(line.strip().split(maxsplit=2)[:2]))
                if predicate(key):
                    # unlinking happens by not writing the line to the new file
                    if verbose:
                        click.echo(f"Unlinked {key} from {filepath}.")
                else:
                    wfile.write(line)
    replace(tmp_filename, filepath)


if __name__ == "__main__":
    cli()
