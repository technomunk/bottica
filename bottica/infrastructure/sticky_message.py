"""
A message that sticks to the bottom of a channel until deletion.
If a message is not the freshes in a channel after an update it will be resent.
"""

from __future__ import annotations

import discord

from bottica.infrastructure.error import atask


class StickyMessage:
    """
    A message that sticks to the bottom of a channel until deletion.
    If a message is not the freshes in a channel after an update it will be resent.
    """

    def __init__(self, message: discord.Message):
        self._message = message

    @classmethod
    async def send(cls, channel: discord.abc.Messageable, content=None, **kwargs) -> StickyMessage:
        """Send a new sticky message."""
        message = await channel.send(content, **kwargs)
        return cls(message)

    async def update(self, content=None, **kwargs):
        channel = self._message.channel
        async for message in channel.history(limit=1):
            if message != self._message:
                atask(self._message.delete())
                self._message = await channel.send(content, **kwargs)
            else:
                atask(self._message.edit(content=content, **kwargs))

    def delete(self):
        atask(self._message.delete())

    # follows the same style as discord API
    # pylint: disable=invalid-name
    @property
    def id(self) -> int:
        return self._message.id

    @property
    def channel(self) -> discord.abc.Messageable:
        return self._message.channel
