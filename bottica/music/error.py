"""Music-specific errors"""
import discord

from bottica.infrastructure.friendly_error import FriendlyError


class AuthorNotVoiceConnectedError(FriendlyError):
    def __init__(self):
        super().__init__("You need to be in a voice channel!")


class AuthorNotInPlayingChannel(FriendlyError):
    def __init__(self):
        super().__init__("You need to be in the same voice channel as me!")


class BotLacksVoicePermissions(FriendlyError):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(f'I lack voice permissions for "{channel.name}"')


class InvalidURLError(FriendlyError):
    def __init__(self):
        super().__init__("Sorry, I can't access that material. Try something else :innocent:")
