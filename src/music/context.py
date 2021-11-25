import enum
import logging
from typing import Any, Dict, Optional, Tuple, cast

import discord
import discord.ext.commands as cmd

from error import atask
from sticky_message import StickyMessage
from util import find_channel, format_duration

from .error import AuthorNotInPlayingChannel
from .file import AUDIO_FOLDER, GUILD_SET_FOLDER, GUILD_STATES_FOLDER
from .song import SongInfo, SongQueue, SongRegistry, SongSet

_logger = logging.getLogger(__name__)


class SongSelectMode(enum.Enum):
    QUEUE = "queue"
    SHUFFLE_QUEUE = "shuffle"
    RADIO = "radio"


class MusicGuildState:
    """Musical state relevant to a single guild."""

    def __init__(self, registry: SongRegistry, guild: discord.Guild) -> None:
        self.guild_id = guild.id
        self.song_set = SongSet(registry, f"{GUILD_SET_FOLDER}{self.guild_id}.txt")
        self.select_queue = SongQueue(registry)
        self.history_queue = SongQueue(registry)

        self.select_mode = SongSelectMode.QUEUE
        self.min_repeat_interval = 32  # sufficiently large number chosen on a whim

        self.song_message: Optional[StickyMessage] = None
        self.last_ctx: Optional[MusicContext] = None

    @property
    def filename(self) -> str:
        return f"{GUILD_STATES_FOLDER}{self.guild_id}.txt"


class MusicContext:
    def __init__(
        self,
        ctx: cmd.Context,
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
        """Join provided voice channel or throw a relevant exception."""
        if self.is_playing() and self.voice_client.channel != channel:  # type: ignore
            raise AuthorNotInPlayingChannel()

        if self.ctx.voice_client is None:
            await channel.connect()
        else:
            await self.voice_client.move_to(channel)  # type: ignore
        self.persist_to_file()

    def disconnect(self):
        if self.voice_client is not None:
            self.voice_client.stop()
            atask(self.voice_client.disconnect())
        self.persist_to_file()

    async def display_current_song_info(self, sticky: bool) -> None:
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
                self.song_message = await StickyMessage.send(self.ctx.channel, embed=embed)
        else:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            atask(self.ctx.send(embed=embed))

    def persist_to_file(self, filename: str = ""):
        filename = filename or self.state.filename
        with open(filename, "w") as file:
            file.write(self.select_mode.value)
            file.write("\n")

            file.write(str(self.min_repeat_interval))
            file.write("\n")

            if self.song_message is not None:
                file.write(f"{self.song_message.ids[0]} {self.song_message.ids[1]}")
            file.write("\n")

            if self.voice_client is not None and self.voice_client.channel is not None:
                file.write(str(self.voice_client.channel.id))
            file.write("\n")

    async def restore_from_file(self, guild: discord.Guild, filename: str = "") -> bool:
        filename = filename or self.state.filename

        try:
            with open(filename, "r") as file:
                self.select_mode = SongSelectMode(file.readline())
                self.min_repeat_interval = int(file.readline())
                line = file.readline()
                if line:
                    ids = cast(Tuple[int, int], tuple(int(id_) for id_ in line.split()))
                    self.song_message = await StickyMessage.from_ids(ids, guild)

                line = file.readline()
                if line:
                    channel = await find_channel(guild, int(line), discord.VoiceChannel)
                    if channel:
                        await channel.connect()

        except Exception as e:
            _logger.exception(e)
            return False

        return True

    def play_next(self) -> None:
        """
        Play the next song in the queue.
        If I'm not playing I will join the issuer's voice channel.
        """
        if self.voice_client is None or self.voice_client.channel is None:
            raise RuntimeError("Bot is not connected to voice to play.")

        if not self.voice_client.is_connected():
            raise RuntimeError("Bot is not connected to a voice channel.")

        song = self.select_next()

        if song is None:
            # clean up after automatic playback
            if self.is_playing():
                self.voice_client.stop()
            if self.song_message:
                self.song_message.delete()
            return

        if self.is_playing():
            self.voice_client.pause()

        def handle_after(error):
            if error is not None:
                _logger.error("encountered error: %s", error)
                return

            if self.voice_client is None:
                # Bottica has already disconnected, no need to raise an error.
                return

            # queue still includes the current song, so check if length is > 1
            if len(self.song_queue) > 1:
                if any(not member.bot for member in self.voice_client.channel.members):
                    self.play_next()
                else:
                    # pause playback. It will be resumed in Cog.on_voice_state_update()
                    if self.song_message is not None:
                        atask(self.song_message.update(embed=discord.Embed(description="...")))
            else:
                if self.song_message is not None:
                    self.song_message.delete()
                    self.song_message = None
                self.song_queue.clear()
                _logger.debug("Disconnecting from %s.", self.ctx.guild.name)
                atask(self.voice_client.disconnect())

        _logger.debug("playing %s in %s", song.key, self.ctx.guild.name)
        self.voice_client.play(
            discord.FFmpegPCMAudio(f"{AUDIO_FOLDER}{song.filename}", options="-vn"),
            after=handle_after,
        )
        if self.song_message:
            atask(self.display_current_song_info(True), self.ctx)

    def select_next(self) -> Optional[SongInfo]:
        """Select the next song to play (mutably)."""
        if self.is_radio:
            if self.song_queue.head is not None:
                self.state.history_queue.push(self.song_queue.head)

            if len(self.state.history_queue) > self.state.min_repeat_interval:
                assert self.state.history_queue.head is not None
                self.song_queue.push(self.state.history_queue.head)

            # Might happen if the min repeat interval is smaller than the guild set
            if len(self.song_queue) <= 1:
                self.song_queue.extend(self.state.history_queue)
                self.state.history_queue.clear()

            return self.song_queue.pop_random()
        else:
            if self.is_shuffling:
                return self.song_queue.pop_random()
            else:
                return self.song_queue.pop()

    @property
    def select_mode(self) -> SongSelectMode:
        return self.state.select_mode

    @select_mode.setter
    def select_mode(self, value: SongSelectMode):
        if self.select_mode == value:
            return

        if value == SongSelectMode.RADIO or self.select_mode == SongSelectMode.RADIO:
            self.state.history_queue.clear()

        if self.select_mode == SongSelectMode.RADIO:
            self.song_queue.clear()

        if value == SongSelectMode.RADIO:
            self.song_queue.clear()
            self.song_queue.extend(self.song_set)

        self.state.select_mode = value
        self.persist_to_file()

    @property
    def min_repeat_interval(self) -> int:
        return self.state.min_repeat_interval

    @min_repeat_interval.setter
    def min_repeat_interval(self, value: int):
        self.state.min_repeat_interval = value
        self.persist_to_file()

    @property
    def song_queue(self) -> SongQueue:
        return self.state.select_queue

    @property
    def song_set(self) -> SongSet:
        return self.state.song_set

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        return self.ctx.voice_client

    @property
    def is_shuffling(self) -> bool:
        return self.select_mode == SongSelectMode.SHUFFLE_QUEUE

    @property
    def is_radio(self) -> bool:
        return self.select_mode == SongSelectMode.RADIO

    @property
    def song_message(self) -> Optional[StickyMessage]:
        return self.state.song_message

    @song_message.setter
    def song_message(self, value: Optional[StickyMessage]):
        self.state.song_message = value
        self.persist_to_file()
