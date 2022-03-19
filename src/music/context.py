from __future__ import annotations

import enum
import logging
from typing import Optional

import discord

from infrastructure.converters import SAVE_CONVERTERS, load_converters
from infrastructure.error import atask
from infrastructure.persist import Field, Persist, infer_field_types
from infrastructure.sticky_message import StickyMessage
from infrastructure.util import format_duration, has_listening_members

from .error import AuthorNotInPlayingChannel
from .file import AUDIO_FOLDER, GUILD_CONTEXT_FOLDER, GUILD_SET_FOLDER
from .song import SongInfo, SongQueue, SongRegistry, SongSet

_logger = logging.getLogger(__name__)


class SongSelectMode(enum.Enum):
    QUEUE = "queue"
    SHUFFLE_QUEUE = "shuffle"
    RADIO = "radio"


SAVE_CONVERTERS[SongSelectMode] = lambda ssm: ssm.value


@infer_field_types
class MusicContext(Persist):
    _select_mode = Field(SongSelectMode.QUEUE)
    min_repeat_interval = Field(32)
    text_channel: Field[discord.TextChannel] = Field()
    _voice_client: Field[Optional[discord.VoiceClient]] = Field(None)
    song_message: Field[Optional[StickyMessage]] = Field(None)

    def __init__(
        self,
        client: discord.Client,
        guild: discord.Guild,
        text_channel: discord.TextChannel,
        voice_client: Optional[discord.VoiceClient],
        registry: SongRegistry,
    ):
        super().__init__()

        self._guild = guild

        self._song_set = SongSet(registry, f"{GUILD_SET_FOLDER}{self._guild.id}.csv")
        self._select_queue = SongQueue(registry)
        self._history_queue = SongQueue(registry)

        self._voice_client = voice_client
        if self._select_mode != SongSelectMode.QUEUE:
            self._update_select_mode(self._select_mode)

        if text_channel is not None:
            self.text_channel = text_channel

    @classmethod
    async def resume(
        cls,
        client: discord.Client,
        guild: discord.Guild,
        registry: SongRegistry,
    ) -> MusicContext:
        mctx = cls(client, guild, None, None, registry)

        await mctx.load(mctx.filename, load_converters(client, mctx))  # type: ignore
        mctx._update_select_mode(mctx._select_mode)

        if mctx._voice_client is not None:
            _logger.debug("resuming playback")
            mctx.play_next()

        return mctx

    def clear(self) -> None:
        """Reset context to a clean state ready for a new play attempt."""
        self._select_queue.clear()
        self._history_queue.clear()
        if self.song_message is not None:
            self.song_message.delete()
        self.song_message = None
        self._select_mode = SongSelectMode.QUEUE
        self.disconnect()
        self.save(self.filename, SAVE_CONVERTERS)

    @property
    def filename(self) -> str:
        return f"{GUILD_CONTEXT_FOLDER}{self._guild.id}.json"

    def is_playing(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_playing()

    def is_paused(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_paused()

    async def join_or_throw(self, channel: discord.VoiceChannel):
        """Join provided voice channel or throw a relevant exception."""
        if self.is_playing() and self._voice_client.channel != channel:  # type: ignore
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

    async def display_current_song_info(
        self,
        sticky: bool,
        channel: Optional[discord.TextChannel] = None,
    ):
        if channel is not None:
            self.text_channel = channel

        song = self.song_queue.head
        if song is None:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            return

        embed = discord.Embed(description=f"{song.pretty_link} <> {format_duration(song.duration)}")

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

    def play_next(self) -> None:
        """
        Play the next song in the queue.
        If I'm not playing I will join the issuer's voice channel.
        """
        if self._voice_client is None or self._voice_client.channel is None:
            raise RuntimeError("Bot is not connected to voice to play.")

        if not self._voice_client.is_connected():
            raise RuntimeError("Bot is not connected to a voice channel.")

        if not has_listening_members(self._voice_client.channel):
            # skip playback. It will be attempted again in Cog.on_voice_state_update()
            _logger.debug("playback skipped due to no active members")
            if self.song_message is not None:
                atask(self.song_message.update(embed=discord.Embed(description="...")))
            return

        song = self.select_next()

        if song is None:
            # clean up after automatic playback
            if self.is_playing():
                self._voice_client.stop()
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            return

        if self.is_playing():
            self._voice_client.pause()

        def handle_after(error):
            if error is not None:
                _logger.error("encountered error: %s", error)
                return

            if self._voice_client is None:
                # Bottica has already disconnected, no need to raise an error.
                return

            # queue still includes the current song, so check if length is > 1
            if len(self._select_queue) > 1:
                self.play_next()
            else:
                if self.song_message is not None:
                    self.song_message.delete()
                    self.song_message = None
                self._select_queue.clear()
                self.disconnect()

        _logger.debug("playing %s in %s", song.key, self._guild.name)
        self._voice_client.play(
            discord.FFmpegPCMAudio(f"{AUDIO_FOLDER}{song.filename}", options="-vn"),
            after=handle_after,
        )
        if self.song_message is not None:
            atask(self.display_current_song_info(True))

    def select_next(self) -> Optional[SongInfo]:
        """Select the next song to play (mutably)."""
        if self.is_radio:
            if self._select_queue.head is not None:
                self._history_queue.push(self._select_queue.head)

            if len(self._history_queue) > self.min_repeat_interval:
                song = self._history_queue.pop()
                assert song is not None
                self._select_queue.push(song)

            # Might happen if the min repeat interval is smaller than the guild set
            if len(self._select_queue) <= 1:
                self._select_queue.extend(self._history_queue)
                self._history_queue.clear()

            return self._select_queue.pop_random()
        else:
            if self.is_shuffling:
                return self._select_queue.pop_random()
            else:
                return self._select_queue.pop()

    def _update_select_mode(self, value: SongSelectMode):
        if value == SongSelectMode.RADIO or self._select_mode == SongSelectMode.RADIO:
            self._history_queue.clear()

        if self._select_mode == SongSelectMode.RADIO:
            self._select_queue.clear()

        if value == SongSelectMode.RADIO:
            self._select_queue.clear()
            self._select_queue.extend(self._song_set)

    @property
    def select_mode(self) -> SongSelectMode:
        return self._select_mode

    @select_mode.setter
    def select_mode(self, value: SongSelectMode):
        if self._select_mode == value:
            return
        self._update_select_mode(value)
        self._select_mode = value

    @property
    def song_queue(self) -> SongQueue:
        return self._select_queue

    @property
    def song_set(self) -> SongSet:
        return self._song_set

    @property
    def is_shuffling(self) -> bool:
        return self._select_mode == SongSelectMode.SHUFFLE_QUEUE

    @property
    def is_radio(self) -> bool:
        return self._select_mode == SongSelectMode.RADIO
