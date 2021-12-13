# Music-playing Cog for the bot

import logging
import random
from os import path
from typing import Dict, Iterable, List, Optional, Tuple

import discord
import discord.ext.commands as cmd
from youtube_dl import YoutubeDL

import response
from error import atask
from music import check
from util import format_duration, has_listening_members, is_listening

from .context import MusicContext, SongSelectMode
from .error import AuthorNotInPlayingChannel, BotLacksVoicePermissions
from .file import AUDIO_FOLDER, DATA_FOLDER, GUILD_CONTEXT_FOLDER, SONG_REGISTRY_FILENAME
from .normalize import normalize_song
from .song import SongInfo, SongRegistry

ALLOWED_INFO_TYPES = ("video", "url")
_logger = logging.getLogger(__name__)


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


class MusicCog(cmd.Cog, name="Music"):  # type: ignore
    def __init__(self, bot: cmd.Bot) -> None:
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
        self.contexts: Dict[int, MusicContext] = {}

        self.bot.status_reporters.append(lambda ctx: self.status(ctx))

    def get_music_context(self, ctx: cmd.Context) -> MusicContext:
        if ctx.guild.id not in self.contexts:
            mctx = MusicContext(ctx.guild, ctx.channel, ctx.voice_client, self.song_registry)
            mctx.persist_to_file()
            self.contexts[ctx.guild.id] = mctx
        return self.contexts[ctx.guild.id]

    @cmd.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            filename = f"{GUILD_CONTEXT_FOLDER}{guild.id}.txt"
            if path.exists(filename):
                try:
                    mctx = MusicContext(guild, None, None, self.song_registry)
                    await mctx.restore_from_file()

                    self.contexts[guild.id] = mctx

                    if mctx.voice_client is not None:
                        _logger.debug("resuming playback")
                        mctx.play_next()

                except Exception as e:
                    _logger.exception(e)
                    _logger.info("guild id: %d", guild.id)

        _logger.info(
            "MusicCog initialized with %d songs and %d states",
            len(self.song_registry),
            len(self.contexts),
        )

    @cmd.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        _before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if after.channel is None:
            return

        mctx = self.contexts.get(after.channel.guild.id)
        if mctx is None or mctx.voice_client is None:
            return

        if member == self.bot.user:
            mctx.update_voice_channel()
            return

        # check that a real user connected to a channel
        if not is_listening(member) or after.channel is None:
            return

        if after.channel == mctx.voice_client.channel:
            if (
                not mctx.is_playing()
                and not mctx.is_paused()
                and has_listening_members(after.channel)
            ):
                await mctx.join_or_throw(after.channel)
                _logger.debug("resuming playback on member connect")
                mctx.play_next()

    def status(self, ctx: cmd.Context) -> Iterable[str]:
        mctx = self.contexts.get(ctx.guild.id)
        if mctx is None:
            return []
        return (
            f"{len(mctx.song_set)} songs in guild set",
            f"Music mode is `{mctx.select_mode.value}`",
        )

    async def _queue_audio(self, ctx: cmd.Context, infos: List[dict]):
        _logger.debug("queueing %s", "playlist" if len(infos) > 1 else "song")
        mctx = self.get_music_context(ctx)

        if mctx.is_shuffling and not mctx.is_playing() and len(infos) > 1:
            _logger.debug("randomizing first song")
            idx = random.randrange(len(infos))
            if idx != 0:
                infos[0], infos[idx] = infos[idx], infos[0]

        for info in infos:
            if info.get("_type", "video") not in ALLOWED_INFO_TYPES:
                embed = discord.Embed(
                    description=f"Skipping {info.get('url')} as it is not a video."
                )
                atask(ctx.reply(embed=embed))
                _logger.warning("Skipping %s as it is a %s", info.get("url"), info["_type"])
                continue
            key = extract_key(info)
            song = self.song_registry.get(key)
            if song is None:
                _logger.debug("downloading '%s'", key)
                song_info = await self.bot.loop.run_in_executor(
                    None, lambda: self.ytdl.process_ie_result(info)
                )
                song = extract_song_info(song_info)
                # normalize song without blocking
                await self.bot.loop.run_in_executor(None, lambda: normalize_song(song))
                self.song_registry.put(song)

            if mctx.song_set.add(song) or not mctx.is_radio:
                mctx.song_queue.push(song)

            if not mctx.is_playing():
                mctx.play_next()

    @cmd.command(aliases=("p",))
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def play(self, ctx: cmd.Context, query: str):
        """
        Play songs found at provided query.
        I will join issuer's voice channel if possible.
        """
        mctx = self.get_music_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)
        # download should be run asynchronously as to avoid blocking the bot
        req = await self.bot.loop.run_in_executor(
            None,
            lambda: self.ytdl.extract_info(query, process=False, download=False),
        )
        req_type = req.get("_type", "video")
        if req_type == "playlist":
            atask(self._queue_audio(ctx, [entry for entry in req["entries"]]), ctx)
        else:
            atask(self._queue_audio(ctx, [req]), ctx)

    @cmd.command(aliases=("pa",))
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def playall(self, ctx: cmd.Context):
        """
        Play all songs that were ever queued on this server.
        I will join issuer's voice channel if possible.
        """
        mctx = self.get_music_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)
        if mctx.is_radio:
            mctx.select_mode = SongSelectMode.SHUFFLE_QUEUE
        mctx.song_queue.extend(mctx.song_set)
        if not mctx.is_playing():
            mctx.play_next()

    @cmd.command()
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def radio(self, ctx: cmd.Context):
        """Start radio play in author's voice channel."""
        mctx = self.get_music_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)
        mctx.select_mode = SongSelectMode.RADIO
        if not mctx.is_playing():
            mctx.play_next()

    @cmd.command()
    @cmd.check(check.bot_is_voice_connected)
    async def pause(self, ctx: cmd.Context):
        """Pause current playback."""
        if not ctx.voice_client.is_paused():
            ctx.voice_client.pause()

    @cmd.command(aliases=("unpause",))
    @cmd.check(check.bot_is_voice_connected)
    async def resume(self, ctx: cmd.Context):
        """Resume paused playback."""
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()

    @cmd.command()
    async def stop(self, ctx: cmd.Context):
        """Stop playback immediately."""
        mctx = self.get_music_context(ctx)
        mctx.disconnect()

    @cmd.command(aliases=("pq",))
    async def purge(self, ctx: cmd.Context):
        """Drop any of the currently queued songs."""
        mctx = self.get_music_context(ctx)
        mctx.song_queue.clear()
        # Radio mode gets broken by cleared queue, switch to queue instead
        mctx.select_mode = SongSelectMode.QUEUE
        mctx.disconnect()

    @cmd.command()
    async def song(self, ctx: cmd.Context, sticky: bool = False):
        """Display information about the current song."""
        mctx = self.get_music_context(ctx)
        if mctx.is_playing() and mctx.song_queue.head is not None:
            atask(mctx.display_current_song_info(sticky, ctx.channel), ctx)
        else:
            atask(ctx.reply("Not playing anything at the moment."))

    @cmd.command(aliases=("q",))
    async def queue(self, ctx: cmd.Context):
        """Display information about the current song queue."""
        mctx = self.get_music_context(ctx)
        if mctx.is_radio:
            desc = f"My radio set consists of {len(mctx.song_set)} songs."
            embed = discord.Embed(description=desc)
            atask(ctx.reply(embed=embed))
        elif mctx.song_queue:
            durstr = format_duration(mctx.song_queue.duration)
            desc = f"I have {len(mctx.song_queue)} songs queued at the moment. ({durstr})"
            embed = discord.Embed(description=desc)
            atask(ctx.reply(embed=embed))
        else:
            atask(ctx.reply("Nothing queued at the moment."))

    @cmd.command(aliases=("mm", "mode"))
    async def music_mode(self, ctx: cmd.Context, mode: Optional[str] = None):
        """
        Manipulate music selection mode. Supports 3 modes:
        - queue : play all queued songs in the order they were queued in.
        - shuffle : play all queued songs in random order.
        - radio : repeatedly play all queued songs in semi-random order, avoiding instant repeats.

        If a mode is not provided I'll just say the current mode :)
        """
        mctx = self.get_music_context(ctx)
        if mode:
            try:
                mctx.select_mode = SongSelectMode(mode)
            except ValueError:
                raise cmd.BadArgument(
                    f"Sorry, I can only be in one of {[e.value for e in SongSelectMode]} modes!"
                )
        else:
            atask(ctx.reply(f"I'm in {mctx.select_mode.value} mode. 😊"))

    @cmd.command(aliases=("n",))
    async def next(self, ctx: cmd.Context):
        """Skip the current song."""
        mctx = self.get_music_context(ctx)
        if not mctx.is_playing():
            atask(ctx.reply("I'm not playing anything." + random.choice(response.FAILS)))
        mctx.play_next()

    @cmd.command(aliases=("j",))
    async def join(self, ctx: cmd.Context, channel: Optional[discord.VoiceChannel] = None):
        """Make Bottica join a given voice channel if provided or issuer's voice channel."""
        if channel is None:
            # rely on exception from provided check
            check.author_is_voice_connected(ctx)
            channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.me)
        if not permissions.connect or not permissions.speak:
            raise BotLacksVoicePermissions(channel)

        mctx = self.get_music_context(ctx)
        try:
            await mctx.join_or_throw(channel)
        except AuthorNotInPlayingChannel as e:
            e.message = "I'm already playing in another channel, please join me instad :kiss:"
            raise e
