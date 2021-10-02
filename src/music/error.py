import discord

from report_err import ReportableError


class AuthorNotVoiceConnectedError(ReportableError):
    def __init__(self):
        super().__init__("You need to be in a voice channel!")


class AuthorNotInPlayingChannel(ReportableError):
    def __init__(self):
        super().__init__("You need to be in the same voice channel as Bottica!")


class BotLacksVoicePermissions(ReportableError):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(f'Bottica lacks voice permissions for "{channel.name}"')
