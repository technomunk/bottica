"""
Collection of inter-dependent state variables required for playing songs in an orderly manner.

Additionally handles state persistence through restarts.
"""
from __future__ import annotations

import logging
from functools import partial
from os import path
from typing import Optional, cast

import discord

from bottica.file import AUDIO_FOLDER, GUILD_CONTEXT_FOLDER, GUILD_SET_FOLDER
from bottica.infrastructure import converters
from bottica.infrastructure.config import GuildConfig
from bottica.infrastructure.error import atask
from bottica.infrastructure.persist import Field, Persist
from bottica.infrastructure.sticky_message import StickyMessage
from bottica.infrastructure.util import format_duration, has_listening_members
from bottica.music.download import streamable_url

from .error import AuthorNotInPlayingChannel
from .song import SongInfo, SongQueue, SongRegistry, SongSet

_logger = logging.getLogger(__name__)


FFMPEG_OPTIONS: dict = {"options": "-vn"}


class SelectSong(Persist):
    shuffle_enabled = Field(False)
    radio_enabled = Field(False)

    def __init__(self, guild_id: int, registry: SongRegistry) -> None:
        super().__init__()

        self._guild_config = GuildConfig(guild_id)
        self._song_set = SongSet(registry, path.join(GUILD_SET_FOLDER, f"{guild_id}.csv"))
        self._queue = SongQueue(registry)
        self._history = SongQueue(registry)
        self._next_song: Optional[SongInfo] = None

    def clear(self) -> None:
        self._queue.clear()
        self._history.clear()
        self.shuffle_enabled = False
        self.radio_enabled = False

    def select_next_song(self) -> Optional[SongInfo]:
        """Select the next song to play (mutably)."""
        song = self._next_song or self._pick_song()
        self._next_song = self._pick_song()
        return song

    def _pick_song(self) -> Optional[SongInfo]:
        if self._queue:
            song = self._queue.pop_random() if self.shuffle_enabled else self._queue.pop()
            assert song

            while len(self._history) > self._guild_config.min_repeat_interval:
                self._history.pop()

            self._history.push(song)
            return song

        if self.radio_enabled:
            return self._song_set.select_random(block_list=self._history)

        return None

    @property
    def next_song(self) -> Optional[SongInfo]:
        return self._next_song

    @property
    def song_queue(self) -> SongQueue:
        return self._queue

    @property
    def song_set(self) -> SongSet:
        return self._song_set


class MusicContext(SelectSong):
    text_channel: Field[discord.TextChannel] = Field(converter=converters.DiscordChannel())
    _voice_client = Field(None, converter=converters.Optional(converters.DiscordVoiceClient()))
    song_message = Field(None, converter=converters.Optional(converters.StickyMessage()))

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

        if text_channel is not None:
            self.text_channel = text_channel

    @classmethod
    async def resume(
        cls,
        client: discord.Client,
        guild: discord.Guild,
        registry: SongRegistry,
    ) -> MusicContext:
        # we know the text channel will get loaded, so hackily ignore invalid state
        mctx = cls(guild, cast(discord.TextChannel, None), None, registry)
        await mctx.load(mctx.filename, client=client)

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
        self.save(self.filename)

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

        duration = format_duration(self._current_song.duration)
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

        self._current_song = self.select_next_song()

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
        audio = await self._audio_source(self._current_song)
        self._voice_client.play(audio, after=partial(self._handle_after))

        if self.song_message is not None:
            atask(self.display_current_song_info(True))

    def _handle_after(self, error: Optional[Exception]) -> None:
        """Command ran after playback has stopped"""
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
            return discord.FFmpegOpusAudio(filepath, **FFMPEG_OPTIONS)

        should_cache = (
            self._guild_config.max_cached_duration == -1
            or song.duration <= self._guild_config.max_cached_duration
        )
        url = await streamable_url(song, should_cache)

        return discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
