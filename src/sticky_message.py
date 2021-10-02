from __future__ import annotations

import discord

from error import atask


class StickyMessage:
    """
    A message that sticks to the bottom of a channel until deletion.
    If a message is not the freshes in a channel after an update it will be resent.
    """

    def __init__(self, message: discord.Message) -> None:
        self._message = message

    @classmethod
    async def send(cls, channel: discord.abc.Messageable, content=None, **kwargs) -> StickyMessage:
        """
        Send a new sticky message.
        """
        message = await channel.send(content, **kwargs)
        return cls(message)

    async def update(self, content=None, **kwargs):
        channel = self._message.channel
        history = await channel.history(limit=1).flatten()
        if history[0] != self._message:
            atask(self._message.delete())
            self._message = await channel.send(content, **kwargs)
        else:
            atask(self._message.edit(content=content, **kwargs))

    def delete(self):
        atask(self._message.delete())
