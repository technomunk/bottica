"""Customized help command."""

from typing import Any

from discord.ext import commands as cmd


class BotticaHelpCommand(cmd.DefaultHelpCommand):
    def get_command_signature(self, command: cmd.Command[Any, ..., Any], /) -> str:
        return super(cmd.DefaultHelpCommand, self).get_command_signature(command)
