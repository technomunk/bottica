from os import makedirs


DATA_FOLDER = "data/"
AUDIO_FOLDER = DATA_FOLDER + "audio/"
GUILD_SET_FOLDER = DATA_FOLDER + ".sets/"
GUILD_CONTEXT_FOLDER = DATA_FOLDER + ".ctx/"
SONG_REGISTRY_FILENAME = DATA_FOLDER + "songs.txt"

makedirs(DATA_FOLDER, exist_ok=True)
makedirs(AUDIO_FOLDER, exist_ok=True)
makedirs(GUILD_SET_FOLDER, exist_ok=True)
makedirs(GUILD_CONTEXT_FOLDER, exist_ok=True)
