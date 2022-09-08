"""
Collection of inter-dependent state variables required for playing songs in an orderly manner.

Additionally handles state persistence through restarts.
"""
from __future__ import annotations

import logging
import os
from functools import partial
from os import path
from typing import Annotated, Optional, cast

import discord

from bottica.file import AUDIO_FOLDER, GUILD_CONTEXT_FOLDER, GUILD_SET_FOLDER
from bottica.infrastructure.config import GuildConfig
from bottica.infrastructure.error import atask
from bottica.infrastructure.sticky_message import StickyMessage
from bottica.infrastructure.util import has_listening_members
from bottica.music.download import download_song
from bottica.music.normalize import stream_normalize_ffmpeg_args
from bottica.util import cmd, fmt
from bottica.util.persist import PERSISTENT, persist, restore

from .error import AuthorNotInPlayingChannel, InvalidURLError
from .song import SongInfo, SongQueue, SongRegistry, SongSet

_logger = logging.getLogger(__name__)


DISCARD_FFMPEG_FLUFF = cmd.join(["-vn", "-sn"])


class SelectSong:
    shuffle_enabled: Annotated[bool, PERSISTENT] = False
    radio_enabled: Annotated[bool, PERSISTENT] = False

    def __init__(self, guild_id: int, registry: SongRegistry) -> None:
        super().__init__()

        self._guild_config = GuildConfig(guild_id)
        self._song_set = SongSet(registry, path.join(GUILD_SET_FOLDER, f"{guild_id}.csv"))
        self._queue = SongQueue(registry)
        self._history = SongQueue(registry)

    def clear(self) -> None:
        self._queue.clear()
        self._history.clear()
        self.shuffle_enabled = False
        self.radio_enabled = False

    def pick_song(self) -> Optional[SongInfo]:
        """Mutably select song from the queue of radio set."""
        song = None

        if self._queue:
            song = self._queue.pop_random() if self.shuffle_enabled else self._queue.pop()

        while len(self._history) > self._guild_config.min_repeat_interval:
            self._history.pop()

        if not song and self.radio_enabled:
            song = self._song_set.select_random(block_list=self._history)

        if song:
            self._history.push(song)

        return song

    @property
    def song_queue(self) -> SongQueue:
        return self._queue

    @property
    def song_set(self) -> SongSet:
        return self._song_set


class MusicContext(SelectSong):
    text_channel: Annotated[discord.TextChannel, PERSISTENT]
    _voice_client: Annotated[Optional[discord.VoiceClient], PERSISTENT] = None
    song_message: Annotated[Optional[StickyMessage], PERSISTENT] = None

    def __init__(
        self,
        guild: discord.Guild,
        text_channel: discord.TextChannel,
        voice_client: Optional[discord.VoiceClient],
        registry: SongRegistry,
    ):
        super().__init__(guild_id=guild.id, registry=registry)

        self._guild = guild

        self._voice_client = voice_client
        self._guild_config = GuildConfig(guild.id)
        self._current_song: Optional[SongInfo] = None
        self._to_cleanup = ""

        if text_channel is not None:
            self.text_channel = text_channel

    @classmethod
    async def restore(
        cls,
        client: discord.Client,
        guild: discord.Guild,
        registry: SongRegistry,
    ) -> MusicContext:
        # we know the text channel will get loaded, so hackily ignore invalid state
        mctx = cls(guild, cast(discord.TextChannel, None), None, registry)
        await restore(mctx.filename, mctx, deserializer_opts={"client": client})

        if mctx._voice_client is not None:
            await mctx.play_next()

        return mctx

    def clear(self) -> None:
        """Reset context to a clean state ready for a new play attempt."""
        super().clear()
        if self.song_message is not None:
            self.song_message.delete()
        self.song_message = None
        self.disconnect()
        persist(self, self.filename)

    @property
    def filename(self) -> str:
        return path.join(GUILD_CONTEXT_FOLDER, f"{self._guild.id}.ctx")

    def is_playing(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_playing()

    def is_paused(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_paused()

    async def join_or_throw(self, channel: discord.VoiceChannel):
        """Join provided voice channel or throw a relevant exception."""
        if (
            self.is_playing()
            and self._voice_client.channel != channel  # type: ignore
            and has_listening_members(self._voice_client.channel)  # type: ignore
        ):
            raise AuthorNotInPlayingChannel()

        if self._voice_client is None:
            self._voice_client = await channel.connect()
        else:
            await self._voice_client.move_to(channel)

    def disconnect(self):
        if self._voice_client is not None:
            self._voice_client.stop()
            atask(self._voice_client.disconnect())
            self._voice_client = None
        self._current_song = None
        self._cleanup_source()

    async def display_current_song_info(
        self,
        sticky: bool,
        channel: Optional[discord.TextChannel] = None,
    ):
        if channel is not None:
            self.text_channel = channel

        if self._current_song is None:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            return

        duration = fmt.duration(self._current_song.duration)
        embed = discord.Embed(description=f"{self._current_song.pretty_link} <> {duration}")

        if sticky:
            if self.song_message is None:
                self.song_message = await StickyMessage.send(self.text_channel, embed=embed)
            else:
                await self.song_message.update(embed=embed)
        else:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            atask(self.text_channel.send(embed=embed))

    async def play_next(self) -> None:
        """
        Play the next song in the queue.
        If I'm not playing I will join the issuer's voice channel.
        """
        if self._voice_client is None or self.voice_channel is None:
            raise RuntimeError("Bot is not connected to voice to play.")

        if not self._voice_client.is_connected():
            raise RuntimeError("Bot is not connected to a voice channel.")

        if not has_listening_members(self.voice_channel):
            # skip playback. It will be attempted again in Cog.on_voice_state_update()
            _logger.debug("playback skipped due to no active members")
            if self.song_message is not None:
                atask(self.song_message.update(embed=discord.Embed(description="...")))
            return

        self._current_song = self.pick_song()
        persist(self, self.filename)

        if self._current_song is None:
            # clean up after automatic playback
            if self.is_playing():
                self._voice_client.stop()
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            return

        if self.is_playing():
            self._voice_client.pause()

        _logger.debug("playing %s in %s", self._current_song.key, self._guild.name)
        try:
            audio = await self._audio_source(self._current_song)
        except InvalidURLError:
            _logger.warning("Song not available: %s", self._current_song.key)
            if self.text_channel:
                msg = f"Sorry. {self._current_song.pretty_link} is not available any more :disappointed:"
                atask(self.text_channel.send(embed=discord.Embed(description=msg)))
            atask(self.play_next())
            return
        self._voice_client.play(audio, after=partial(self._handle_after))

        if self.song_message is not None:
            atask(self.display_current_song_info(True))

    def _handle_after(self, error: Optional[Exception]) -> None:
        """Command ran after playback has stopped"""
        self._cleanup_source()

        self._current_song = None
        if error is not None:
            _logger.error("encountered error: %s", error)
            return

        if self._voice_client is None:
            # Bottica has already disconnected, no need to raise an error.
            return

        # queue still includes the current song, so check if length is > 1
        if len(self._queue) > 1 or self.radio_enabled:
            atask(self.play_next())
        else:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            self.disconnect()

    @property
    def voice_channel(self) -> Optional[discord.VoiceChannel]:
        if self._voice_client is None:
            return None
        return cast(discord.VoiceChannel, self._voice_client.channel)

    def update_voice_client(self, client: discord.VoiceClient) -> None:
        """
        Update the internal voice client to the provided one.
        Used for correcting state after re-connecting.
        """
        self._voice_client = client

    async def _audio_source(self, song: SongInfo) -> discord.FFmpegAudio:
        filepath = path.join(AUDIO_FOLDER, song.filename)
        if path.exists(filepath):
            return discord.FFmpegOpusAudio(filepath, before_options=DISCARD_FFMPEG_FLUFF)

        cache = (
            self._guild_config.max_cached_duration == -1
            or song.duration <= self._guild_config.max_cached_duration
        )
        source = await download_song(song, cache)

        self._to_cleanup = source
        return discord.FFmpegPCMAudio(
            source,
            before_options=DISCARD_FFMPEG_FLUFF,
            options=stream_normalize_ffmpeg_args(),
        )

    def _cleanup_source(self) -> None:
        if not self._to_cleanup:
            return

        try:
            os.remove(self._to_cleanup)
        except (OSError, FileNotFoundError):
            pass

        self._to_cleanup = ""
