"""Music-playing Cog for the bot"""

import logging
import random
from functools import partial
from os import path
from typing import Iterable, Optional, cast

import discord
import discord.ext.commands as cmd

from bottica import response
from bottica.file import GUILD_CONTEXT_FOLDER, SONG_REGISTRY_FILENAME
from bottica.infrastructure.check import guild_only
from bottica.infrastructure.command import command
from bottica.infrastructure.config import GuildConfig
from bottica.infrastructure.error import atask
from bottica.infrastructure.friendly_error import FriendlyError
from bottica.infrastructure.util import has_listening_members
from bottica.music import check
from bottica.util import fmt
from bottica.util.persist import persist

from .context import MusicContext
from .download import process_request
from .error import AuthorNotInPlayingChannel, BotLacksVoicePermissions
from .song import SongInfo, SongRegistry

ALLOWED_INFO_TYPES = ("video", "url")
_logger = logging.getLogger(__name__)


# This is user-facing API, so it's fine
# pylint: disable=too-many-public-methods
class Music(cmd.Cog):
    def __init__(self, bot: cmd.Bot) -> None:
        self.bot = bot
        self.song_registry = SongRegistry(SONG_REGISTRY_FILENAME)
        self.contexts: dict[int, MusicContext] = {}

        self.bot.status_reporters.append(partial(self.status))  # type: ignore

    def get_music_context(self, ctx: cmd.Context) -> MusicContext:
        assert ctx.guild is not None
        assert isinstance(ctx.channel, discord.TextChannel)
        if ctx.guild.id not in self.contexts:
            mctx = MusicContext(
                self.bot,
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
                    mctx = await MusicContext.restore(self.bot, guild, self.song_registry)
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
        _logger.debug("saving...")
        for mctx in self.contexts.values():
            persist(mctx, mctx.filename)

    @cmd.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member == self.bot.user:
            return

        if not isinstance(after.channel, discord.VoiceChannel):
            return

        if after.channel is None or not has_listening_members(after.channel):
            return

        guild_id = after.channel.guild.id
        mctx = self.contexts.get(guild_id)
        if mctx is None or mctx.is_playing() or mctx.is_paused():
            return

        try_resume = mctx.voice_channel == after.channel

        if before.channel is None:
            try:
                song = self.get_announcement(guild_id, member.id)
                if song is not None:
                    await mctx.join_or_throw(after.channel)
                    await mctx.play_announcement(song)
                    return
            except FriendlyError:
                pass

        if try_resume:
            await mctx.join_or_throw(after.channel)
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

    @command(aliases=["p"], descriptions={"url": "of the song to play"})
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    @guild_only
    async def play(self, ctx: cmd.Context, url: str):
        """
        Play songs found at provided query.
        I will join issuer's voice channel if possible.
        """
        mctx = self.get_music_context(ctx)
        await mctx.join_or_throw(ctx.author.voice.channel)  # type: ignore

        songs = await process_request(url)

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

    @command(aliases=["pa"])
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    @guild_only
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

    @command(descriptions={"enabled": "..."})
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    @guild_only
    async def shuffle(
        self,
        ctx: cmd.Context,
        enabled: Optional[bool] = None,
    ):
        """Enable, disable or check shuffle mode."""
        mctx = self.get_music_context(ctx)
        if enabled is None:
            atask(ctx.reply(f"Shuffling is {fmt.onoff(mctx.shuffle_enabled)}"))
            return

        mctx.shuffle_enabled = enabled

    @command(descriptions={"enabled": "..."})
    @cmd.check(check.bot_has_voice_permission_in_author_channel)
    @guild_only
    async def radio(
        self,
        ctx: cmd.Context,
        enabled: Optional[bool] = None,
    ):
        """Enable, disable or check radio mode."""
        mctx = self.get_music_context(ctx)
        if enabled is None:
            atask(ctx.reply(f"Radio mode is {fmt.onoff(mctx.radio_enabled)}"))
            return

        mctx.radio_enabled = enabled
        if enabled and not mctx.is_playing():
            await mctx.join_or_throw(ctx.author.voice.channel)  # type: ignore
            await mctx.play_next()

    @command()
    @guild_only
    async def reset(self, ctx: cmd.Context):
        """Let me gather my thoughts before trying again."""
        mctx = self.get_music_context(ctx)
        mctx.clear()

    @command()
    @cmd.check(check.bot_is_voice_connected)
    @guild_only
    async def pause(self, ctx: cmd.Context) -> None:
        """Pause current playback."""
        if ctx.voice_client is None:
            return

        voice_client = cast(discord.VoiceClient, ctx.voice_client)
        if not voice_client.is_paused():
            voice_client.pause()

    @command(aliases=["unpause"])
    @cmd.check(check.bot_is_voice_connected)
    @guild_only
    async def resume(self, ctx: cmd.Context) -> None:
        """Resume paused playback."""
        if ctx.voice_client is None:
            return

        voice_client = cast(discord.VoiceClient, ctx.voice_client)
        if voice_client.is_paused():
            voice_client.resume()

    @command()
    @guild_only
    async def stop(self, ctx: cmd.Context):
        """Stop playback immediately."""
        mctx = self.get_music_context(ctx)
        mctx.disconnect()

    @command(aliases=["pq"])
    @guild_only
    async def clear(self, ctx: cmd.Context):
        """Drop any of the currently queued songs."""
        mctx = self.get_music_context(ctx)
        mctx.song_queue.clear()
        mctx.disconnect()

    @command(descriptions={"sticky": "keep the message updated as the song changes"})
    @guild_only
    async def song(self, ctx: cmd.Context, sticky: bool = False) -> None:
        """Display information about the current song."""
        if not isinstance(ctx.channel, discord.TextChannel):
            return

        mctx = self.get_music_context(ctx)
        if mctx.is_playing():
            atask(mctx.display_current_song_info(sticky, ctx.channel), ctx)
        else:
            atask(ctx.reply("Not playing anything at the moment."))

    @command(aliases=["q"])
    @guild_only
    async def queue(self, ctx: cmd.Context):
        """Display information about the current song queue."""
        mctx = self.get_music_context(ctx)
        if mctx.song_queue:
            durstr = fmt.duration(mctx.song_queue.duration)
            desc = f"I have {len(mctx.song_queue)} songs queued at the moment. ({durstr})"
            embed = discord.Embed(description=desc)
            atask(ctx.reply(embed=embed))
        elif mctx.radio_enabled:
            description = f"My radio set consists of {len(mctx.song_set)} songs."
            embed = discord.Embed(description=description)
            atask(ctx.reply(embed=embed))
        else:
            atask(ctx.reply("Nothing queued at the moment."))

    @command(aliases=["n", "skip"])
    @guild_only
    async def next(self, ctx: cmd.Context):
        """Skip the current song."""
        mctx = self.get_music_context(ctx)
        if not mctx.is_playing() and not mctx.radio_enabled:
            atask(ctx.reply("I'm not playing anything." + random.choice(response.FAILS)))
            return
        await mctx.play_next()

    @command(aliases=["j"], descriptions={"channel": "to join"})
    @guild_only
    async def join(
        self,
        ctx: cmd.Context,
        channel: Optional[discord.VoiceChannel] = None,
    ):
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

    @command(
        aliases=["sa", "seta", "set_announcement"],
        descriptions={"member": "user to announce", "url": "of the announcement song"},
    )
    @guild_only
    async def announcement(
        self,
        ctx: cmd.Context,
        member: Optional[discord.Member] = None,
        url: str = "",
    ) -> None:
        """Set the provided song to be played when the user (or you) enters a voice channel."""
        assert ctx.guild is not None

        songs = await process_request(url)

        if not songs:
            raise FriendlyError("Sorry, I couldn't find anything. :sweat_smile:")

        if len(songs) > 1:
            raise FriendlyError(
                "Hey bud. It's a few too many, try just one announcement for now, ok?",
            )

        guild_config = GuildConfig.get(ctx.guild.id)
        user = member or ctx.author
        self.song_registry.put(songs[0])
        guild_config.announcements[user.id] = songs[0].key
        persist(guild_config, guild_config.filename)

    @command(
        aliases=["ca", "cleara"],
        descriptions={"member": "user to remove the announcement for"},
    )
    @guild_only
    async def clear_announcement(
        self,
        ctx: cmd.Context,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Remove the associated announcement song with the provided user (or you)."""
        assert ctx.guild is not None
        guild_config = GuildConfig.get(ctx.guild.id)
        user = member or ctx.author
        del guild_config.announcements[user.id]
        persist(guild_config, guild_config.filename)

    def get_announcement(self, guild_id: int, member_id: int) -> Optional[SongInfo]:
        """Get the announcement associated with provided member id at the provided guild."""
        song_key = GuildConfig.get(guild_id).announcements.get(member_id)
        if song_key is None:
            return None

        song = self.song_registry.get(song_key)
        if song is None:
            raise FriendlyError(
                "Sorry, I couldn't find your announcement. Please set it again :sweat:",
            )
        return song

    @command(aliases=["a"], descriptions={"member": "user to announce with a song"})
    @guild_only
    async def announce(
        self,
        ctx: cmd.Context,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Play the announcement associated with provided guild member of you."""
        assert ctx.guild is not None
        assert isinstance(ctx.author, discord.Member)

        mctx = self.get_music_context(ctx)
        if mctx.is_playing():
            raise FriendlyError("I'm already playing something.")

        if mctx.voice_channel is None:
            if ctx.author.voice is None or not isinstance(
                ctx.author.voice.channel,
                discord.VoiceChannel,
            ):
                raise FriendlyError("You won't hear me ^^;")
            await mctx.join_or_throw(ctx.author.voice.channel)

        member = member or ctx.author
        song = self.get_announcement(ctx.guild.id, member.id)
        if song is None:
            raise FriendlyError("Looks like you don't have an announcement set :smile:")

        await mctx.play_announcement(song)

    @command(
        descriptions={"channels": "One or more voice channels where I'm allowed to play music."}
    )
    @guild_only
    async def restrict_to(self, ctx: cmd.Context, *channels: discord.VoiceChannel):
        """Tell me which channels I'm allowed to play music in. If you set it to None - I'll play music anywhere!"""
        assert ctx.guild is not None
        guild_config = GuildConfig.get(ctx.guild.id)
        if channels:
            guild_config.music_channels = [channel.id for channel in channels]
            message = "Ok, I'll stick to only those channels!"
        else:
            guild_config.music_channels = []
            message = "Alright, I'll play music anywhere ^^"

        await ctx.reply(message)
