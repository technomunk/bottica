
import logging
from typing import Any, Dict, Optional

import discord
import discord.ext.commands as cmd

from error import atask
from sticky_message import StickyMessage
from util import format_duration

from .error import AuthorNotInPlayingChannel
from .file import AUDIO_FOLDER, GUILD_SET_FOLDER
from .song import SongQueue, SongRegistry, SongSet

_logger = logging.getLogger(__name__)


class MusicGuildState:
    """Musical state relevant to a single guild."""

    __slots__ = ("queue", "set", "is_shuffling", "song_message", "last_ctx")

    def __init__(self, registry: SongRegistry, guild_id: int) -> None:
        self.queue = SongQueue(registry)
        self.set = SongSet(registry, f"{GUILD_SET_FOLDER}{guild_id}.txt")
        self.is_shuffling = False
        self.song_message: Optional[StickyMessage] = None
        self.last_ctx: Optional[MusicContext] = None


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

    async def display_current_song_info(self, active: bool) -> None:
        song = self.song_queue.head
        if song is None:
            if self.song_message is not None:
                atask(self.song_message.delete())
            return

        embed = discord.Embed(description=f"{song.pretty_link} <> {format_duration(song.duration)}")

        if active:
            if self.song_message is not None:
                atask(self.song_message.update(embed=embed))
            else:
                self.song_message = await StickyMessage.send(self.ctx.channel, embed=embed)
        else:
            if self.song_message is not None:
                self.song_message.delete()
                self.song_message = None
            atask(self.ctx.send(embed=embed))

    def play_next(self) -> None:
        """
        Play the next song in the queue.
        If I'm not playing I will join the issuer's voice channel.
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
            # clean up after automatic playback
            if self.is_playing():
                self.voice_client.stop()
            if self.song_message:
                atask(self.song_message.delete())
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
    def song_message(self) -> Optional[StickyMessage]:
        return self.state.song_message

    @song_message.setter
    def song_message(self, value: Optional[StickyMessage]):
        self.state.song_message = value
