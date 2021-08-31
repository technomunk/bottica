# Music-playing Cog for the bot

import itertools
import logging
import random
from collections import deque
from os import makedirs, path, scandir
from typing import Deque, Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from youtube_dl import YoutubeDL

import response

DATA_FOLDER = "data/"
AUDIO_FOLDER = DATA_FOLDER + "audio/"
LISTS_FOLDER = DATA_FOLDER + "lists/"

logger = logging.getLogger(__name__)


class AuthorNotVoiceConnectedError(commands.CommandError):
    def __init__(self) -> None:
        super().__init__(message="You need to be in a voice channel!")


async def check_author_is_voice_connected(ctx: commands.Context) -> bool:
    if ctx.author.voice is None:
        raise AuthorNotVoiceConnectedError()

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()
    else:
        await ctx.voice_client.move_to(ctx.author.voice.channel)
    return True


def check_author_is_dj(ctx: commands.Context) -> bool:
    return "@dj" in ctx.author.roles


Playlist = Dict[str, Tuple[str, str]]


def parse_playlist(filename: str) -> Playlist:
    def parse_line(line: str):
        els = line.split(maxsplit=3)
        return (f"{els[0]}_{els[1]}", (els[2], els[3].strip()))

    with open(filename, "r", encoding="utf8") as file:
        return dict(parse_line(line) for line in file)


def _initialize_playlists() -> Dict[str, Optional[Playlist]]:
    result: Dict[str, Optional[Playlist]] = dict()
    if path.exists(LISTS_FOLDER):
        with scandir(LISTS_FOLDER) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith(".txt"):
                    result[entry.name[:-4]] = None
    else:
        makedirs(LISTS_FOLDER)

    playlist_all_filename = LISTS_FOLDER + "all.txt"
    if "all" in result:
        result["all"] = parse_playlist(playlist_all_filename)
    else:
        with open(playlist_all_filename, "w", encoding="utf8") as file:
            assert file
        result["all"] = dict()
    return result


def genname(info: dict) -> str:
    """
    Generate name for a given song.
    """
    info_type = info.get("_type", "video")
    if info_type not in ("video", "url"):
        raise NotImplementedError(f"genname(info['_type']: '{info_type}')")
    domain = info.get("ie_key", info.get("extractor_key")).lower()
    return f"{domain}_{info['id']}"


def genline(info: dict) -> str:
    """
    Generate playlist entry line for a given song.
    """
    domain = info.get("ie_key", info.get("extractor_key")).lower()
    return " ".join((domain, info["id"], info["ext"], info["title"]))


def genlink(song: str) -> str:
    """
    Generate a clickable link to the song with provided id.
    """
    [domain, id] = song.split("_", maxsplit=1)
    if domain != "youtube":
        raise NotImplementedError("genlink(song: domain != youtube)")
    return f"https://www.{domain}.com/watch?v={id}"


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        ytdl_options = {
            "format": "bestaudio",
            "outtmpl": AUDIO_FOLDER + "%(extractor)s_%(id)s.%(ext)s",
            "cachedir": DATA_FOLDER + "dlcache",
            "ignoreerrors": True,
            "cookiefile": DATA_FOLDER + "cookies.txt",
            "quiet": True,
        }
        self.ytdl = YoutubeDL(ytdl_options)
        self.current_song: Optional[Tuple[str, str]] = None
        self.song_queue: Deque[Tuple[str, str]] = deque()
        self.voice_client = None
        self.is_shuffling = False
        self.playlists = _initialize_playlists()
        assert self.playlists["all"] is not None
        logger.debug("MusicCog initialized with %d songs", len(self.playlists["all"]))

    def _update_playlist(self, playlist: str, song_name: str, song_info: dict):
        if self.playlists[playlist] is None:
            raise NotImplementedError("_update_playlist(new)")
        update_file = False
        if song_name in self.playlists[playlist]:
            update_file = True
        self.playlists[playlist][song_name] = (song_info["ext"], song_info["title"])
        if update_file:
            raise NotImplementedError("update file in _update_playlist()")
        else:
            with open(f"{LISTS_FOLDER}{playlist}.txt", "a", encoding="utf8") as file:
                file.write(genline(song_info))
                file.write("\n")

    async def _queue_audio(self, infos: List[dict]):
        logger.debug("queueing audio")

        if self.is_shuffling and not self.is_playing() and len(infos) > 1:
            idx = random.randrange(1, len(infos))
            infos[0], infos[idx] = infos[idx], infos[0]

        for info in infos:
            name = genname(info)
            assert self.playlists["all"] is not None
            song = self.playlists["all"].get(name)
            if song:
                self.song_queue.append((name, song[0]))
            else:
                song_info = await self.bot.loop.run_in_executor(
                    None, lambda: self.ytdl.process_ie_result(info)
                )
                self._update_playlist("all", name, song_info)
                self.song_queue.append((name, song_info["ext"]))
            if not self.is_playing():
                self.play_next()

    def is_playing(self):
        return self.voice_client is not None and self.voice_client.is_playing()

    @commands.command(aliases=("p",))
    @commands.check(check_author_is_voice_connected)
    async def play(self, ctx: commands.Context, query: str):
        """
        Play songs found at provided query.
        """
        self.voice_client = ctx.voice_client
        # download should be run asynchronously as to avoid blocking the bot
        req = await self.bot.loop.run_in_executor(
            None,
            lambda: self.ytdl.extract_info(query, process=False, download=False),
        )
        req_type = req.get("_type", "video")
        if req_type == "playlist":
            await self._queue_audio([entry for entry in req["entries"]])
        else:
            await self._queue_audio([req])

    @commands.command(aliases=("pa",))
    @commands.check(check_author_is_voice_connected)
    async def playall(self, ctx: commands.Context):
        """
        Play all downloaded songs.
        """
        self.voice_client = ctx.voice_client
        playlist = self.playlists["all"]
        assert playlist is not None
        self.song_queue.extend((song, playlist[song][0]) for song in playlist)
        if not self.is_playing():
            self.play_next()

    @commands.command(aliases=("q",))
    async def queue(self, ctx: commands.Context):
        """
        List queued songs.
        """
        MAX_LEN = 10
        if self.is_playing() and self.current_song is not None:
            idx = 0
            resp = ""
            for name, _ in itertools.chain((self.current_song,), self.song_queue):
                assert self.playlists["all"] is not None
                _, title = self.playlists["all"][name]
                resp += f"{idx}: [{title}]({genlink(name)})\n"
                idx += 1
                if idx >= MAX_LEN:
                    break
            title = f"Song queue ({idx}/{len(self.song_queue)+1})"
            await ctx.reply(embed=discord.Embed(title=title, description=resp))
        else:
            await ctx.reply("Nothing is queued at the moment.")

    @commands.command()
    async def shuffle(self, ctx: commands.context):
        """
        Toggle shuffling of the queued playlist.
        """
        self.is_shuffling = not self.is_shuffling
        if self.is_shuffling:
            resp = "Shuffling queued songs."
        else:
            resp = "Playing queued songs in order."
        await ctx.reply(resp)

    @commands.command(aliases=("n",))
    async def next(self, ctx: commands.Context):
        """
        Skip the current song.
        """
        if not self.is_playing():
            return await ctx.reply(
                "I'm not playing anything." + random.choice(response.FAILS)
            )
        self.play_next()

    def play_next(self):
        """
        Play the next song in the queue.
        """
        if self.voice_client is None or self.voice_client.channel is None:
            raise RuntimeError("Bot is not connected to voice to play.")

        if not self.voice_client.is_connected():
            raise RuntimeError("Bot is not connected to a voice chennel.")

        if not self.song_queue:
            if self.is_playing():
                self.voice_client.stop()
            self.current_song = None
            return

        if self.is_shuffling:
            idx = random.randrange(len(self.song_queue))
            name, ext = self.song_queue[idx]
            del self.song_queue[idx]
        else:
            name, ext = self.song_queue.popleft()

        if not name:
            raise RuntimeError("Attempted to play an empty file!")

        if self.is_playing():
            self.voice_client.pause()

        def handle_after(error):
            if error is None:
                self.play_next()
            else:
                logger.error("encountered error: %s", error)

        logger.debug("playing %s", name)
        self.voice_client.play(
            discord.FFmpegPCMAudio(f"{AUDIO_FOLDER}{name}.{ext}", options="-vn"),
            after=handle_after,
        )
        self.current_song = (name, ext)
