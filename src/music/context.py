from __future__ import annotations

import enum
import logging
from typing import Optional

import discord

from error import atask
from sticky_message import StickyMessage
from util import find_channel, format_duration

from .error import AuthorNotInPlayingChannel
from .file import AUDIO_FOLDER, GUILD_CONTEXT_FOLDER, GUILD_SET_FOLDER
from .song import SongInfo, SongQueue, SongRegistry, SongSet

_logger = logging.getLogger(__name__)


class SongSelectMode(enum.Enum):
    QUEUE = "queue"
    SHUFFLE_QUEUE = "shuffle"
    RADIO = "radio"


class MusicContext:
    __slots__ = (
        "_guild",
        "_song_set",
        "_select_queue",
        "_history_queue",
        "_select_mode",
        "_min_repeat_interval",
        "_text_channel",
        "_song_message",
        "_voice_client",
    )

    def __init__(
        self,
        guild: discord.Guild,
        voice_client: Optional[discord.VoiceClient],
        registry: SongRegistry,
    ):
        self._guild = guild
        self._song_set = SongSet(registry, f"{GUILD_SET_FOLDER}{self._guild.id}.txt")

        self._select_queue = SongQueue(registry)
        self._history_queue = SongQueue(registry)

        self._select_mode = SongSelectMode.QUEUE
        self._min_repeat_interval = 32  # sufficiently large number chosen on a whim

        self._text_channel: discord.TextChannel = None
        self._song_message: Optional[StickyMessage] = None
        self._voice_client = voice_client

    @property
    def filename(self) -> str:
        return f"{GUILD_CONTEXT_FOLDER}{self._guild.id}.txt"

    def is_playing(self) -> bool:
        return self._voice_client is not None and self._voice_client.is_playing()

    async def join_or_throw(self, channel: discord.VoiceChannel):
        """Join provided voice channel or throw a relevant exception."""
        if self.is_playing() and self.voice_client.channel != channel:  # type: ignore
            raise AuthorNotInPlayingChannel()

        if self._voice_client is None:
            self._voice_client = await channel.connect()
        else:
            await self._voice_client.move_to(channel)  # type: ignore
        self.persist_to_file()

    def persist_to_file(self):
        with open(self.filename, "w") as file:
            file.write(self._select_mode.value)
            file.write("\n")

            file.write(str(self._min_repeat_interval))
            file.write("\n")

            file.write(str(self._text_channel.id))
            file.write("\n")

            if self.song_message is not None:
                file.write(str(self.song_message.id))
            file.write("\n")

            if self._voice_client is not None and self._voice_client.channel is not None:
                file.write(str(self._voice_client.channel.id))
            file.write("\n")

    async def restore_from_file(self):
        # Note that all the assignments are direct and don't use self. properties
        with open(self.filename, "r") as file:
            self._select_mode = SongSelectMode(file.readline().strip())
            self._min_repeat_interval = int(file.readline().strip())

            channel_id = int(file.readline().strip())
            channel = find_channel(self._guild, channel_id, discord.TextChannel)
            assert channel is not None
            self._text_channel = channel

            line = file.readline().strip()
            if line:
                message_id = int(file.readline().strip())
                message = await self._text_channel.fetch_message(message_id)
                self._song_message = StickyMessage(message)

            line = file.readline().strip()
            if line:
                channel = await find_channel(self._guild, int(line), discord.VoiceChannel)
                if channel is not None:
                    self.voice_client = await channel.connect()

    def disconnect(self):
        if self._voice_client is not None:
            self._voice_client.stop()
            atask(self._voice_client.disconnect())
        self.persist_to_file()

    async def display_current_song_info(
        self,
        sticky: bool,
        channel: Optional[discord.TextChannel] = None,
    ):
        if channel is not None:
            self._text_channel = channel

        song = self.song_queue.head
        if song is None:
            if self.song_message is not None:
                atask(self.song_message.delete())
            return

        embed = discord.Embed(description=f"{song.pretty_link} <> {format_duration(song.duration)}")

        if sticky:
            if self.song_message is not None:
                atask(self.song_message.update(embed=embed))
            else:
                self.song_message = await StickyMessage.send(self._text_channel, embed=embed)
        else:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            atask(self._text_channel.send(embed=embed))

    def play_next(self) -> None:
        """
        Play the next song in the queue.
        If I'm not playing I will join the issuer's voice channel.
        """
        if self._voice_client is None or self._voice_client.channel is None:
            raise RuntimeError("Bot is not connected to voice to play.")

        if not self._voice_client.is_connected():
            raise RuntimeError("Bot is not connected to a voice channel.")

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
                if any(not member.bot for member in self._voice_client.channel.members):
                    self.play_next()
                else:
                    # pause playback. It will be resumed in Cog.on_voice_state_update()
                    if self.song_message is not None:
                        atask(self.song_message.update(embed=discord.Embed(description="...")))
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
        if self.song_message:
            atask(self.display_current_song_info(True))

    def select_next(self) -> Optional[SongInfo]:
        """Select the next song to play (mutably)."""
        if self.is_radio:
            if self._select_queue.head is not None:
                self._history_queue.push(self._select_queue.head)

            if len(self._history_queue) > self._min_repeat_interval:
                assert self._history_queue.head is not None
                self._select_queue.push(self._history_queue.head)

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

    @property
    def select_mode(self) -> SongSelectMode:
        return self._select_mode

    @select_mode.setter
    def select_mode(self, value: SongSelectMode):
        if self._select_mode == value:
            return

        if value == SongSelectMode.RADIO or self._select_mode == SongSelectMode.RADIO:
            self._history_queue.clear()

        if self._select_mode == SongSelectMode.RADIO:
            self._select_queue.clear()

        if value == SongSelectMode.RADIO:
            self._select_queue.clear()
            self._select_queue.extend(self._song_set)

        self._select_mode = value
        self.persist_to_file()

    @property
    def min_repeat_interval(self) -> int:
        return self._min_repeat_interval

    @min_repeat_interval.setter
    def min_repeat_interval(self, value: int):
        self._min_repeat_interval = value
        self.persist_to_file()

    @property
    def song_queue(self) -> SongQueue:
        return self._select_queue

    @property
    def song_set(self) -> SongSet:
        return self._song_set

    @property
    def is_shuffling(self) -> bool:
        return self.select_mode == SongSelectMode.SHUFFLE_QUEUE

    @property
    def is_radio(self) -> bool:
        return self.select_mode == SongSelectMode.RADIO

    @property
    def song_message(self) -> Optional[StickyMessage]:
        return self.song_message

    @song_message.setter
    def song_message(self, value: Optional[StickyMessage]):
        self.song_message = value
        self.persist_to_file()
