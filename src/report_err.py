import discord.ext.commands as cmd


class ReportableError(cmd.CommandError):
    """
    An error that should be reported to the user as is.
    """

    def __init__(self, message, *args):
        super().__init__(message=message, *args)
