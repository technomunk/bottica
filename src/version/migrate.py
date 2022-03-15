"""
Run migration from specified version.
"""

import os
from typing import List

from music.file import GUILD_SET_FOLDER, SONG_REGISTRY_FILENAME

from .old_song import OLD_SONG_REGISTRY_FILENAME, convert_old_song_registry, convert_old_song_set


def migrate_0_16() -> List[str]:
    convert_old_song_registry(OLD_SONG_REGISTRY_FILENAME, SONG_REGISTRY_FILENAME)
    print(OLD_SONG_REGISTRY_FILENAME, "=>", SONG_REGISTRY_FILENAME)
    files_to_remove = [OLD_SONG_REGISTRY_FILENAME]

    for guild_set in os.listdir(GUILD_SET_FOLDER):
        old_filename = GUILD_SET_FOLDER + guild_set
        name, _ = os.path.splitext(old_filename)
        new_filename = f"{name}.csv"
        convert_old_song_set(old_filename, new_filename)
        print(guild_set, "=>", new_filename)

        files_to_remove.append(old_filename)

    return files_to_remove


MIGRATIONS = {
    "0.16.0": migrate_0_16,
}
