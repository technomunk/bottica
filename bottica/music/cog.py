"""Music-playing Cog for the bot"""

import logging
import random
from functools import partial
from os import path
from typing import Dict, Iterable, Optional, cast

import discord
import discord.ext.commands as cmd

from bottica import response
from bottica.file import GUILD_CONTEXT_FOLDER, SONG_REGISTRY_FILENAME
from bottica.infrastructure.error import atask
from bottica.infrastructure.util import format_duration, has_listening_members, is_listening, onoff
from bottica.music import check

from .context import MusicContext
from .download import process_request
from .error import AuthorNotInPlayingChannel, BotLacksVoicePermissions
from .song import SongRegistry

ALLOWED_INFO_TYPES = ("video", "url")
_logger = logging.getLogger(__name__)


class Music(cmd.Cog):
    def __init__(self, bot: cmd.Bot) -> None:
        self.bot = bot
        self.song_registry = SongRegistry(SONG_REGISTRY_FILENAME)
        self.contexts: Dict[int, MusicContext] = {}

        self.bot.status_reporters.append(partial(self.status))  # type: ignore

    def get_music_context(self, ctx: cmd.Context) -> MusicContext:
        assert ctx.guild is not None
        assert isinstance(ctx.channel, discord.TextChannel)
        if ctx.guild.id not in self.contexts:
            mctx = MusicContext(
                ctx.guild,
                ctx.channel,
                cast(discord.VoiceClient, ctx.voice_client),
                self.song_registry,
            )
            self.contexts[ctx.guild.id] = mctx
        return self.contexts[ctx.guild.id]

    @cmd.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            filename = path.join(GUILD_CONTEXT_FOLDER, f"{guild.id}.ctx")
            if path.exists(filename):
                try:
                    mctx = await MusicContext.resume(self.bot, guild, self.song_registry)
                    self.contexts[guild.id] = mctx

                # In this case, we indeed want to catch any and all non-exit exceptions and log them
                # pylint: disable=broad-except
                except Exception as e:
                    _logger.exception(e)
                    _logger.info("guild id: %d", guild.id)

        _logger.info(
            "MusicCog initialized with %d songs and %d states",
            len(self.song_registry),
            len(self.contexts),
        )

    @cmd.Cog.listener()
    async def on_resumed(self):
        for voice_client in self.bot.voice_clients:
            if isinstance(voice_client, discord.VoiceClient):
                if mctx := self.contexts.get(voice_client.guild):
                    _logger.debug("Updating MCTX voice client for %s", voice_client.guild.name)
                    mctx.update_voice_client(voice_client)

    async def close(self):
        for mctx in self.contexts.values():
            mctx.save(mctx.filename)

    @cmd.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if not isinstance(after.channel, discord.VoiceChannel):
            return

        if after.channel:
            guild_id = after.channel.guild.id
        elif isinstance(before, discord.VoiceChannel) and before.channel:
            guild_id = before.channel.guild.id  # type: ignore
        else:
            return

        mctx = self.contexts.get(guild_id)
        if mctx is None or mctx.voice_channel is None:
            return

        if member == self.bot.user:
            return

        # check that a real user connected to a channel
        if not is_listening(member) or after.channel is None:
            return

        if after.channel == mctx.voice_channel:
            if (
                not mctx.is_playing()
                and not mctx.is_paused()
                and has_listening_members(after.channel)
            ):
                await mctx.join_or_throw(after.channel)
                _logger.debug("resuming playback on member connect")
                await mctx.play_next()

    def status(self, ctx: cmd.Context) -> Iterable[str]:
        if ctx.guild is None:
            return []

        mctx = self.contexts.get(ctx.guild.id)
        if mctx is None:
            return []

        music_mode_status = f"Music mode is `{'shuffle' if mctx.shuffle_enabled else 'queue'}`"
        if mctx.radio_enabled:
            music_mode_status += " with `radio`"

        return (
            f"{len(mctx.song_set)} songs in guild set",
            music_mode_status,
        )

    @cmd.command(aliases=["p"])
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def play(self, ctx: cmd.Context, url: str):
        """
        Play songs found at provided query.
        I will join issuer's voice channel if possible.
        """
        mctx = self.get_music_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)  # type: ignore

        songs = await process_request(url)
        songs = list(songs)

        if mctx.shuffle_enabled and not mctx.is_playing() and len(songs) > 1:
            _logger.debug("randomizing first song")
            idx = random.randrange(len(songs))
            if idx != 0:
                songs[0], songs[idx] = songs[idx], songs[0]

        for song in songs:
            self.song_registry.put(song)

            mctx.song_set.add(song)
            mctx.song_queue.push(song)

            if not mctx.is_playing():
                await mctx.play_next()

    @cmd.command(aliases=["pa"])
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def playall(self, ctx: cmd.Context):
        """
        Play all songs that were ever queued on this server.
        I will join issuer's voice channel if possible.
        """
        mctx = self.get_music_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)  # type: ignore
        mctx.song_queue.extend(mctx.song_set)
        if not mctx.is_playing():
            await mctx.play_next()

    @cmd.command()
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def shuffle(self, ctx: cmd.Context, enabled: Optional[bool] = None):
        """Enable, disable or check shuffle mode."""
        mctx = self.get_music_context(ctx)
        if enabled is None:
            atask(ctx.reply(f"Shuffle is {onoff(mctx.shuffle_enabled)}."))
            return
        mctx.shuffle_enabled = enabled

    @cmd.command()
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    async def radio(self, ctx: cmd.Context, enabled: Optional[bool] = None):
        """
        Enable or disable radio mode.

        If radio mode is enabled - I will play songs you asked for earlier instead of going quiet.
        """
        mctx = self.get_music_context(ctx)
        if enabled is None:
            atask(ctx.reply(f"Radio mode is {onoff(mctx.radio_enabled)}"))
            return
        mctx.radio_enabled = enabled
        if enabled and not mctx.is_playing():
            await mctx.join_or_throw(ctx.author.voice.channel)  # type: ignore
            await mctx.play_next()

    @cmd.command()
    async def reset(self, ctx: cmd.Context):
        """Let me gather my thoughts before trying again."""
        mctx = self.get_music_context(ctx)
        mctx.clear()

    @cmd.command()
    @cmd.check(check.bot_is_voice_connected)
    async def pause(self, ctx: cmd.Context) -> None:
        """Pause current playback."""
        if ctx.voice_client is None:
            return

        voice_client = cast(discord.VoiceClient, ctx.voice_client)
        if not voice_client.is_paused():
            voice_client.pause()

    @cmd.command(aliases=["unpause"])
    @cmd.check(check.bot_is_voice_connected)
    async def resume(self, ctx: cmd.Context) -> None:
        """Resume paused playback."""
        if ctx.voice_client is None:
            return

        voice_client = cast(discord.VoiceClient, ctx.voice_client)
        if voice_client.is_paused():
            voice_client.resume()

    @cmd.command()
    async def stop(self, ctx: cmd.Context):
        """Stop playback immediately."""
        mctx = self.get_music_context(ctx)
        mctx.disconnect()

    @cmd.command(aliases=["pq"])
    async def clear(self, ctx: cmd.Context):
        """Drop any of the currently queued songs."""
        mctx = self.get_music_context(ctx)
        mctx.song_queue.clear()
        mctx.disconnect()

    @cmd.command()
    async def song(self, ctx: cmd.Context, sticky: bool = False) -> None:
        """Display information about the current song."""
        if not isinstance(ctx.channel, discord.TextChannel):
            return

        mctx = self.get_music_context(ctx)
        if mctx.is_playing():
            atask(mctx.display_current_song_info(sticky, ctx.channel), ctx)
        else:
            atask(ctx.reply("Not playing anything at the moment."))

    @cmd.command(aliases=["q"])
    async def queue(self, ctx: cmd.Context):
        """Display information about the current song queue."""
        mctx = self.get_music_context(ctx)
        if mctx.song_queue:
            durstr = format_duration(mctx.song_queue.duration)
            desc = f"I have {len(mctx.song_queue)} songs queued at the moment. ({durstr})"
            embed = discord.Embed(description=desc)
            atask(ctx.reply(embed=embed))
        elif mctx.radio_enabled:
            description = f"My radio set consists of {len(mctx.song_set)} songs."
            embed = discord.Embed(description=description)
            atask(ctx.reply(embed=embed))
        else:
            atask(ctx.reply("Nothing queued at the moment."))

    @cmd.command(aliases=["n", "skip"])
    async def next(self, ctx: cmd.Context):
        """Skip the current song."""
        mctx = self.get_music_context(ctx)
        if not mctx.is_playing() and not mctx.radio_enabled:
            atask(ctx.reply("I'm not playing anything." + random.choice(response.FAILS)))
            return
        await mctx.play_next()

    @cmd.command(aliases=["j"])
    async def join(self, ctx: cmd.Context, channel: Optional[discord.VoiceChannel] = None):
        """Make Bottica join a given voice channel if provided or issuer's voice channel."""
        if channel is None:
            # rely on exception from provided check
            check.author_is_voice_connected(ctx)
            channel = ctx.author.voice.channel  # type: ignore
        channel = cast(discord.VoiceChannel, channel)
        permissions = channel.permissions_for(ctx.me)  # type: ignore
        if not permissions.connect or not permissions.speak:
            raise BotLacksVoicePermissions(channel)

        mctx = self.get_music_context(ctx)
        try:
            await mctx.join_or_throw(channel)
        except AuthorNotInPlayingChannel as e:
            e.message = "I'm already playing in another channel, please join me instad :kiss:"
            raise e
