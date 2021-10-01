# Music-playing Cog for the bot

import logging
import random
from os import makedirs
from typing import Any, Dict, Iterable, List, Optional, Tuple

import discord
from discord.ext import commands
from youtube_dl import YoutubeDL

import response
from error import atask
from song import SongInfo, SongQueue, SongRegistry, SongSet
from util import format_duration, onoff

DATA_FOLDER = "data/"
AUDIO_FOLDER = DATA_FOLDER + "audio/"
GUILD_SET_FOLDER = DATA_FOLDER + ".sets/"
SONG_REGISTRY_FILENAME = DATA_FOLDER + "songs.txt"

logger = logging.getLogger(__name__)


class AuthorNotVoiceConnectedError(commands.CommandError):
    def __init__(self) -> None:
        super().__init__(message="You need to be in a voice channel!")


class AuthorNotInPlayingChannel(commands.CommandError):
    def __init__(self):
        super().__init__(message="You need to be in the same channel as playing Bottica!")


async def check_author_is_voice_connected(ctx: commands.Context) -> bool:
    if ctx.author.voice is None:
        raise AuthorNotVoiceConnectedError()
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


class MusicGuildState:
    """
    Musical state relevant to a single guild.
    """

    __slots__ = ("queue", "set", "is_shuffling", "song_message", "last_ctx")

    def __init__(self, registry: SongRegistry, guild_id: int) -> None:
        self.queue = SongQueue(registry)
        self.set = SongSet(registry, f"{GUILD_SET_FOLDER}{guild_id}.txt")
        self.is_shuffling = False
        self.song_message: Optional[discord.Message] = None
        self.last_ctx: Optional[MusicContext] = None


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
        self.state.last_ctx = self

    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    def __getattr__(self, name: str) -> Any:
        if name in self.__dict__:
            return getattr(self, name)
        return getattr(self.ctx, name)

    async def join_or_throw(self, channel: discord.VoiceChannel):
        """
        Join provided voice channel or throw a relevant exception.
        """
        if all(
            (
                self.is_playing(),
                self.voice_client,
                self.voice_client.channel != channel,  # type: ignore
            )
        ):
            raise AuthorNotInPlayingChannel()

        if self.ctx.voice_client is None:
            await channel.connect()
        else:
            await self.voice_client.move_to(channel)  # type: ignore

    async def display_current_song_info(self, active: bool) -> None:
        song = self.song_queue.head
        if song is None:
            if self.song_message is not None:
                atask(self.song_message.delete())
            return

        embed = discord.Embed(description=f"{song.pretty_link} <> {format_duration(song.duration)}")

        reuse = False
        if active and self.song_message is not None:
            hist = await self.ctx.history(limit=1).flatten()
            reuse = hist[0] == self.song_message

        if reuse:
            assert self.song_message is not None
            atask(self.song_message.edit(embed=embed))
        elif active:
            # repost a message to the bottom of a channel so that it's easier to see
            if self.song_message:
                atask(self.song_message.delete())
            self.song_message = await self.ctx.send(embed=embed)
        else:
            self.song_message = None
            atask(self.ctx.reply(embed=embed))

    def play_next(self) -> None:
        """
        Play the next song in the queue.
        If Bottica is not playing she will join the issuer's voice channel.
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
                atask(self.song_message.delete())
            return

        if self.is_playing():
            self.voice_client.pause()

        def handle_after(error):
            if error is not None:
                logger.error("encountered error: %s", error)
                return

            if any(not member.bot for member in self.voice_client.channel.members):
                self.play_next()
            elif self.song_message:
                if len(self.song_queue) > 1:
                    atask(self.song_message.edit(embed=discord.Embed(description="...")))
                else:
                    atask(self.song_message.delete())

        logger.debug("playing %s in %s", song.key, self.ctx.guild.name)
        self.voice_client.play(
            discord.FFmpegPCMAudio(f"{AUDIO_FOLDER}{song.filename}", options="-vn"),
            after=handle_after,
        )
        if self.song_message:
            atask(self.display_current_song_info(True), self.ctx)

    @property
    def song_queue(self) -> SongQueue:
        return self.state.queue

    @property
    def song_set(self) -> SongSet:
        return self.state.set

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


class MusicCog(commands.Cog, name="Music"):  # type: ignore
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
        self.song_registry = SongRegistry(SONG_REGISTRY_FILENAME)
        self.guild_states: Dict[int, MusicGuildState] = {}

        makedirs(AUDIO_FOLDER, exist_ok=True)
        makedirs(GUILD_SET_FOLDER, exist_ok=True)

    def _wrap_context(self, ctx: commands.Context) -> MusicContext:
        return MusicContext(ctx, self.song_registry, self.guild_states)

    @commands.Cog.listener()
    async def on_ready(self):
        self.guild_states = {
            guild.id: MusicGuildState(self.song_registry, guild.id) for guild in self.bot.guilds
        }
        logger.info(
            "MusicCog initialized with %d songs and %d states",
            len(self.song_registry),
            len(self.guild_states),
        )
        self.bot.status_reporters.append(lambda ctx: self.status(ctx))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        _before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # check that a real user connected to a channel
        if member.bot or after.channel is None:
            return
        state = self.guild_states.get(after.channel.guild.id)
        if any((state is None, state.last_ctx is None, state.last_ctx.voice_client is None)):  # type: ignore
            return
        if after.channel == state.last_ctx.voice_client.channel:
            if not state.last_ctx.is_playing():
                state.last_ctx.play_next()
                logger.debug("resuming playback")

    def status(self, ctx: commands.Context) -> Iterable[str]:
        state = self.guild_states[ctx.guild.id]
        return (
            f"{len(state.set)} songs in guild set",
            f"Shuffling is `{onoff(state.is_shuffling)}`",
        )

    async def _queue_audio(self, ctx: MusicContext, infos: List[dict]):
        logger.debug("queueing %s", "playlist" if len(infos) > 1 else "song")

        if ctx.is_shuffling and not ctx.is_playing() and len(infos) > 1:
            logger.debug("randomizing first song")
            idx = random.randrange(len(infos))
            if idx != 0:
                infos[0], infos[idx] = infos[idx], infos[0]

        for info in infos:
            if info.get("_type", "video") != "video":
                embed = discord.Embed(
                    description=f"Skipping {info.get('url')} as it is not a video."
                )
                atask(ctx.ctx.reply(embed=embed))
                logger.warning("Skipping %s as it is a %s", info.get("url"), info["_type"])
                continue
            key = extract_key(info)
            song = self.song_registry.get(key)
            if song is None:
                logger.debug("downloading '%s'", key)
                song_info = await self.bot.loop.run_in_executor(
                    None, lambda: self.ytdl.process_ie_result(info)
                )
                song = extract_song_info(song_info)
                self.song_registry.put(song)
            ctx.song_set.add(song)
            ctx.song_queue.push(song)
            if not ctx.is_playing():
                ctx.play_next()

    @commands.command(aliases=("p",))
    @commands.check(check_author_is_voice_connected)
    async def play(self, ctx: commands.Context, query: str):
        """
        Play songs found at provided query.
        Bottica will join issuer's voice channel if possible.
        """
        mctx = self._wrap_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)
        # download should be run asynchronously as to avoid blocking the bot
        req = await self.bot.loop.run_in_executor(
            None,
            lambda: self.ytdl.extract_info(query, process=False, download=False),
        )
        req_type = req.get("_type", "video")
        if req_type == "playlist":
            atask(self._queue_audio(mctx, [entry for entry in req["entries"]]), ctx)
        else:
            atask(self._queue_audio(mctx, [req]), ctx)

    @commands.command(aliases=("pa",))
    @commands.check(check_author_is_voice_connected)
    async def playall(self, ctx: commands.Context):
        """
        Play all songs that were ever queued on this server.
        Bottica will join issuer's voice channel if possible.
        """
        mctx = self._wrap_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)
        mctx.song_queue.extend(mctx.song_set)
        if not mctx.is_playing():
            mctx.play_next()

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
        mctx = self._wrap_context(ctx)
        mctx.song_queue.clear()
        if ctx.voice_client is not None:
            ctx.voice_client.stop()

    @commands.command()
    async def song(self, ctx: commands.Context, active: bool = False):
        """
        Display information about the current song.
        """
        mctx = self._wrap_context(ctx)
        if mctx.is_playing() and mctx.song_queue.head is not None:
            atask(mctx.display_current_song_info(active), ctx)
        else:
            atask(ctx.reply("Not playing anything at the moment."))

    @commands.command(aliases=("q",))
    async def queue(self, ctx: commands.Context):
        """
        Display information about the current song queue.
        """
        mctx = self._wrap_context(ctx)
        if mctx.is_playing() and mctx.song_queue:
            durstr = format_duration(mctx.song_queue.duration)
            desc = f"Queued {len(mctx.song_queue)} songs ({durstr})."
            embed = discord.Embed(description=desc)
            atask(ctx.reply(embed=embed))
        else:
            atask(ctx.reply("Nothing queued at the moment."))

    @commands.command()
    async def shuffle(self, ctx: commands.context, state: Optional[bool] = None):
        """
        Manipulate whether the queued songs should be shuffled.
        Sets the shuffling of the queue to provided value or prints whether the queue
        is currently being shuffled. While the queue is shuffled the songs will come
        in random order.
        """
        mctx = self._wrap_context(ctx)
        if state is None:
            atask(ctx.reply(f"Shuffling is `{onoff(mctx.is_shuffling)}`"))
        else:
            mctx.is_shuffling = state

    @commands.command(aliases=("n",))
    async def next(self, ctx: commands.Context):
        """
        Skip the current song.
        """
        mctx = self._wrap_context(ctx)
        if not mctx.is_playing():
            atask(ctx.reply("I'm not playing anything." + random.choice(response.FAILS)))
        mctx.play_next()
