"""Metadata file structure"""
from os import makedirs, path

DATA_FOLDER = "data"
AUDIO_FOLDER = path.join(DATA_FOLDER, "audio")
GUILD_SET_FOLDER = path.join(DATA_FOLDER, ".sets")
GUILD_CONTEXT_FOLDER = path.join(DATA_FOLDER, ".ctx")
GUILD_CONFIG_FOLDER = path.join(DATA_FOLDER, ".cfg")
SONG_REGISTRY_FILENAME = path.join(DATA_FOLDER, "songs.csv")

for folder in (
    AUDIO_FOLDER,
    GUILD_SET_FOLDER,
    GUILD_CONTEXT_FOLDER,
    GUILD_CONFIG_FOLDER,
):
    makedirs(folder, exist_ok=True)
