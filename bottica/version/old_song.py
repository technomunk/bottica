"""Old SongInfo structure for migration-capability"""
import csv
from dataclasses import asdict, astuple
from os import path

from bottica.file import DATA_FOLDER
from bottica.music.song import FILE_ENCODING, SongCSVDialect, SongInfo, SongKey

OLD_SONG_REGISTRY_FILENAME = path.join(DATA_FOLDER, "songs.txt")


def convert_old_song_registry(old_filename: str, new_filename: str):
    """
    Create a song file in latest format from an older version.
    Does not modify old file.
    """
    with (
        open(old_filename, "r", encoding=FILE_ENCODING) as old_file,
        open(new_filename, "w", encoding=FILE_ENCODING) as new_file,
    ):
        writer = csv.writer(new_file, SongCSVDialect)
        header_exists = False

        for line in old_file:
            song = _parse_old_song_line(line)
            if not header_exists:
                writer.writerow(asdict(song).keys())
                header_exists = True

            writer.writerow(astuple(song))


def convert_old_song_set(old_filename: str, new_filename: str):
    with (
        open(old_filename, "r", encoding=FILE_ENCODING) as old_file,
        open(new_filename, "w", encoding=FILE_ENCODING) as new_file,
    ):
        writer = csv.writer(new_file, SongCSVDialect)
        header_exists = False
        for line in old_file:
            song_key = _parse_old_song_key(line)
            if not header_exists:
                writer.writerow(["domain", "id"])
                header_exists = True
            writer.writerow(song_key)


def _parse_old_song_line(line: str) -> SongInfo:
    domain, intradomain_id, _, dur, title = line.strip().split(maxsplit=4)
    duration = int(dur)
    return SongInfo(domain, intradomain_id, duration, title)


def _parse_old_song_key(line: str) -> SongKey:
    domain, intradomain_id = line.strip().split(maxsplit=2)[:2]
    return domain, intradomain_id
