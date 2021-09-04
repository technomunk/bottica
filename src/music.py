# Music-playing Cog for the bot

import logging
import random
from dataclasses import dataclass
from os import makedirs
from typing import Any, Coroutine, Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from youtube_dl import YoutubeDL

import response
from song import SongSet, SongInfo, SongQueue, SongRegistry
from util import format_duration, onoff

DATA_FOLDER = "data/"
AUDIO_FOLDER = DATA_FOLDER + "audio/"
GUILD_SET_FOLDER = DATA_FOLDER + ".sets/"
SONG_REGISTRY_FILENAME = DATA_FOLDER + "songs.txt"

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
    return "@dj" in (role.name for role in ctx.author.roles)


def check_bot_is_voice_connected(ctx: commands.Context) -> bool:
    return ctx.voice_client is not None and ctx.voice_client.is_connected()


def extract_key(info: dict) -> Tuple[str, str]:
    """
    Generate key for a given song.
    """
    info_type = info.get("_type", "video")
    if info_type not in ("video", "url"):
        raise NotImplementedError(f"genname(info['_type']: '{info_type}')")
    domain = info.get("ie_key", info.get("extractor_key")).lower()
    return (domain, info["id"])


def extract_song_info(info: dict) -> SongInfo:
    domain, id = extract_key(info)
    return SongInfo(domain, id, info["ext"], info["duration"], info["title"])


@dataclass
class MusicGuildState:
    """
    Musical state relevant to a single guild.
    """
    __slots__ = ("queue", "song_set", "is_shuffling", "song_message")
    queue: SongQueue
    song_set: SongSet
    is_shuffling: bool = False
    song_message: Optional[discord.Message] = None

    def __init__(self, registry: SongRegistry, guild_id: int) -> None:
        self.queue = SongQueue(registry)
        self.song_set = SongSet(registry, f"{GUILD_SET_FOLDER}{guild_id}.txt")


class MusicContext:
    def __init__(
        self,
        ctx: commands.Context,
        registry: SongRegistry,
        states: Dict[int, MusicGuildState],
    ) -> None:
        self.ctx = ctx
        if ctx.guild.id not in states:
            states[ctx.guild.id] = MusicGuildState(registry, ctx.guild.id)
        self.state = states[ctx.guild.id]

    def is_playing(self) -> bool:
        return (
            self.ctx.voice_client is not None
            and self.ctx.voice_client.is_playing()
        )

    def task(self, task: Coroutine) -> None:
        self.ctx.bot.loop.create_task(task)

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__:
            return getattr(self, name)
        return getattr(self.ctx, name)

    async def display_current_song_info(self, active: bool) -> None:
        song = self.song_queue.head
        if song is None:
            if self.song_message is not None:
                self.task(self.song_message.delete())
            return

        embed = discord.Embed(description=song.pretty_link)

        reuse = False
        if active and self.song_message is not None:
            hist = await self.ctx.history(limit=1).flatten()
            reuse = hist[0] == self.song_message

        if reuse:
            assert self.song_message is not None
            self.task(self.song_message.edit(embed=embed))
        elif active:
            if self.song_message:
                self.task(self.song_message.delete())
            self.song_message = await(self.ctx.send(embed=embed))
        else:
            self.song_message = None
            self.task(self.ctx.send(embed=embed))

    def play_next(self) -> None:
        """
        Play the next song in the queue.
        """
        if self.voice_client is None or self.voice_client.channel is None:
            raise RuntimeError("Bot is not connected to voice to play.")

        if not self.voice_client.is_connected():
            raise RuntimeError("Bot is not connected to a voice channel.")

        if self.is_shuffling:
            song = self.song_queue.pop_random()
        else:
            song = self.song_queue.pop()

        if song is None:
            if self.is_playing():
                self.voice_client.stop()
            if self.song_message:
                self.task(self.song_message.delete())
            return

        if self.is_playing():
            self.voice_client.pause()

        def handle_after(error):
            if error is None:
                self.play_next()
            else:
                logger.error("encountered error: %s", error)

        logger.debug("playing %s", song.key)
        self.voice_client.play(
            discord.FFmpegPCMAudio(f"{AUDIO_FOLDER}{song.filename}", options="-vn"),
            after=handle_after,
        )
        if self.song_message:
            self.task(self.display_song_info(True))

    @property
    def song_queue(self) -> SongQueue:
        return self.state.queue

    @property
    def song_set(self) -> SongSet:
        return self.state.song_set

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        return self.ctx.voice_client

    @property
    def is_shuffling(self) -> bool:
        return self.state.is_shuffling

    @is_shuffling.setter
    def is_shuffling(self, value: bool) -> None:
        self.state.is_shuffling = value

    @property
    def song_message(self) -> Optional[discord.Message]:
        return self.state.song_message

    @song_message.setter
    def song_message(self, value: Optional[discord.Message]):
        self.state.song_message = value


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
        self.songs = SongRegistry(SONG_REGISTRY_FILENAME)
        self.guild_states: Dict[int, MusicGuildState] = {}

        makedirs(AUDIO_FOLDER, exist_ok=True)
        makedirs(GUILD_SET_FOLDER, exist_ok=True)

        bot.status_reporters.append(lambda ctx: self.status(ctx))
        logger.debug("MusicCog initialized with %d songs", len(self.songs))

    def _wrap_context(self, ctx: commands.Context) -> MusicContext:
        return MusicContext(ctx, self.registry, self.guild_states)

    def status(self, ctx: commands.Context) -> str:
        is_shuffling = self.guild_states[ctx.guild.id].is_shuffling
        return f"with {len(self.songs)} songs at the ready\nshuffling is {onoff(is_shuffling)}"

    async def _queue_audio(self, ctx: MusicContext, infos: List[dict]):
        logger.debug("queueing %s", "playlist" if len(infos) > 1 else "song")

        if ctx.is_shuffling and not ctx.is_playing() and len(infos) > 1:
            logger.debug("randomizing first song")
            idx = random.randrange(len(infos))
            if idx != 0:
                infos[0], infos[idx] = infos[idx], infos[0]

        for info in infos:
            key = extract_key(info)
            song = self.songs.get(key)
            if song is None:
                logger.debug("downloading '%s'", key)
                song_info = await self.bot.loop.run_in_executor(
                    None, lambda: self.ytdl.process_ie_result(info)
                )
                song = extract_song_info(song_info)
                self.songs.put(song)
            ctx.song_set.add(song)
            ctx.song_queue.push(song)
            if not ctx.is_playing():
                ctx.play_next()

    @commands.command(aliases=("p",))
    @commands.check(check_author_is_voice_connected)
    async def play(self, ctx: commands.Context, query: str):
        """
        Play songs found at provided query.
        """
        # download should be run asynchronously as to avoid blocking the bot
        req = await self.bot.loop.run_in_executor(
            None,
            lambda: self.ytdl.extract_info(query, process=False, download=False),
        )
        req_type = req.get("_type", "video")
        ctx = self._wrap_context(ctx)
        if req_type == "playlist":
            self.bot.loop.create_task(
                self._queue_audio(ctx, [entry for entry in req["entries"]])
            )
        else:
            self.bot.loop.create_task(self._queue_audio(ctx, [req]))

    @commands.command(aliases=("pa",))
    @commands.check(check_author_is_voice_connected)
    async def playall(self, ctx: commands.Context):
        """
        Play all songs that were ever queued on this server.
        """
        ctx = self._wrap_context(ctx)
        ctx.song_queue.extend(ctx.song_set)
        if not ctx.is_playing():
            self.play_next()

    @commands.command()
    @commands.check(check_bot_is_voice_connected)
    async def pause(self, ctx: commands.Context):
        """
        Pause current playback.
        """
        if not ctx.voice_client.is_paused():
            ctx.voice_client.pause()

    @commands.command(aliases=("unpause",))
    @commands.check(check_bot_is_voice_connected)
    async def resume(self, ctx: commands.Context):
        """
        Resume paused playback.
        """
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()

    @commands.command(aliases=("pq",))
    @commands.check(check_author_is_dj)
    async def purge(self, ctx: commands.Context):
        """
        Drop any songs queued for playback.
        """
        ctx = self._wrap_context(ctx)
        ctx.song_queue.clear()
        if ctx.voice_client is not None:
            ctx.voice_client.stop()

    @commands.command()
    async def song(self, ctx: commands.Context, active: bool = False):
        """
        Display information about the current song.
        """
        ctx = self._wrap_context(ctx)
        if ctx.is_playing() and ctx.song_queue.head is not None:
            self.bot.loop.create_task(ctx.display_song_info(active))
        else:
            self.bot.loop.create_task(
                ctx.reply("Not playing anything at the moment.")
            )

    @commands.command(aliases=("q",))
    async def queue(self, ctx: commands.Context):
        """
        Display information about the current song queue.
        """
        ctx = self._wrap_context(ctx)
        if ctx.is_playing() and ctx.song_queue:
            durstr = format_duration(ctx.song_queue.duration)
            desc = f"Queued {len(ctx.song_queue)} songs ({durstr})."
            embed = discord.Embed(description=desc)
            self.bot.loop.create_task(ctx.reply(embed=embed))
        else:
            self.bot.loop.create_task(ctx.reply("Nothing queued at the moment."))

    @commands.command()
    async def shuffle(self, ctx: commands.context, state: Optional[bool] = None):
        """
        Toggle shuffling of the queued playlist.
        """
        ctx = self._wrap_context(ctx)
        if state is None:
            self.bot.loop.create_task(
                ctx.reply(f"Shuffling is {onoff(ctx.is_shuffling)}")
            )
        else:
            ctx.is_shuffling = state

    @commands.command(aliases=("n",))
    async def next(self, ctx: commands.Context):
        """
        Skip the current song.
        """
        ctx = self._wrap_context(ctx)
        if not ctx.is_playing():
            self.bot.loop.create_task(
                ctx.reply("I'm not playing anything." + random.choice(response.FAILS))
            )
        ctx.play_next()
