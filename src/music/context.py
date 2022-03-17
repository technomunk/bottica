from __future__ import annotations

import enum
import logging
from typing import Optional

import discord

from infrastructure.error import atask
from infrastructure.persist import Persist, PersistedVar
from infrastructure.serializers import DiscordChannelSerializer, EnumSerializer, OptionalSerializer
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


class MusicContext(Persist):
    _select_mode = PersistedVar(SongSelectMode.QUEUE, serializer=EnumSerializer(SongSelectMode))
    min_repeat_interval = PersistedVar(32)
    text_channel = PersistedVar(serializer=DiscordChannelSerializer(discord.TextChannel))
    _song_message_id = PersistedVar(0)
    _voice_channel = PersistedVar(
        None,
        serializer=OptionalSerializer(DiscordChannelSerializer(discord.VoiceChannel)),
    )

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

        self._song_message: Optional[StickyMessage] = None

        # Make sure the more complex serializers are useable
        type(self).text_channel.serializer.finalize(client=client)
        type(self)._voice_channel.serializer.finalize(client=client)

        self.load()

        self._voice_client = voice_client
        if self._select_mode != SongSelectMode.QUEUE:
            self._update_select_mode(self._select_mode)

        if text_channel is not None:
            self.text_channel = text_channel
        if voice_client is not None:
            self._voice_channel = voice_client.channel

    @classmethod
    async def resume(
        cls,
        client: discord.Client,
        guild: discord.Guild,
        registry: SongRegistry,
    ) -> MusicContext:
        mctx = cls(client, guild, None, None, registry)

        if mctx._song_message_id:
            await mctx.fetch_song_message()

        if mctx._voice_channel is not None:
            mctx._voice_client = await mctx._voice_channel.connect()
            _logger.debug("resuming playback")
            mctx.play_next()
        else:
            mctx._song_message_id = 0

        return mctx

    def clear(self):
        """Reset context to a clean state ready for a new play attempt."""
        self.save_on_update = False
        self._select_queue.clear()
        self._history_queue.clear()
        self._song_message = None
        self._select_mode = SongSelectMode.QUEUE
        self.disconnect()
        self.save_on_update = True
        self.save()

    @property
    def filename(self) -> str:
        return f"{GUILD_CONTEXT_FOLDER}{self._guild.id}.json"

    def is_playing(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_playing()

    def is_paused(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_paused()

    async def join_or_throw(self, channel: discord.VoiceChannel):
        """Join provided voice channel or throw a relevant exception."""
        if self.is_playing() and self.voice_client.channel != channel:  # type: ignore
            raise AuthorNotInPlayingChannel()

        if self._voice_client is None:
            self._voice_client = await channel.connect()
        else:
            await self._voice_client.move_to(channel)
        self._voice_channel = self._voice_client.channel

    def disconnect(self):
        if self._voice_client is not None:
            self._voice_client.stop()
            atask(self._voice_client.disconnect())
            self._voice_client = None
            self._voice_channel = None

    async def display_current_song_info(
        self,
        sticky: bool,
        channel: Optional[discord.TextChannel] = None,
    ):
        song_message = await self.fetch_song_message()

        if channel is not None:
            self.text_channel = channel

        song = self.song_queue.head
        if song is None:
            if song_message is not None:
                song_message.delete()

            self._song_message = None
            self._song_message_id = 0
            return

        embed = discord.Embed(description=f"{song.pretty_link} <> {format_duration(song.duration)}")

        if sticky:
            if song_message is None:
                self._song_message = await StickyMessage.send(self.text_channel, embed=embed)
                self._song_message.id_update_callback = lambda: self._update_song_id()
            else:
                await song_message.update(embed=embed)
        else:
            if song_message is not None:
                song_message.delete()
                self._song_message = None
            atask(self.text_channel.send(embed=embed))

        self._update_song_id()

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
            if self._song_message is not None:
                atask(self._song_message.update(embed=discord.Embed(description="...")))
            return

        song = self.select_next()

        if song is None:
            # clean up after automatic playback
            if self.is_playing():
                self._voice_client.stop()
            if self._song_message:
                self._song_message.delete()
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
                if self._song_message is not None:
                    self._song_message.delete()
                    self._song_message = None
                    self._update_song_id()
                self._select_queue.clear()
                self.disconnect()

        _logger.debug("playing %s in %s", song.key, self._guild.name)
        self._voice_client.play(
            discord.FFmpegPCMAudio(f"{AUDIO_FOLDER}{song.filename}", options="-vn"),
            after=handle_after,
        )
        if self._song_message:
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

    async def fetch_song_message(self) -> Optional[StickyMessage]:
        if self._song_message:
            return self._song_message

        if self.text_channel and self._song_message_id:
            message = await self.text_channel.fetch_message(self._song_message_id)
            if message:
                self._song_message = StickyMessage(message, lambda: self._update())
            else:
                self._song_message = None

        if self._song_message is None:
            self._song_message_id = 0

        return self._song_message

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        return self._voice_client

    def _update_song_id(self):
        self._song_message_id = self._song_message.id if self._song_message else 0
