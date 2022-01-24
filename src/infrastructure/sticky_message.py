from __future__ import annotations

from typing import Callable, Optional

import discord

from infrastructure.error import atask


class StickyMessage:
    """
    A message that sticks to the bottom of a channel until deletion.
    If a message is not the freshes in a channel after an update it will be resent.
    """

    def __init__(self, message: discord.Message, id_update_callback: Optional[Callable] = None):
        self._message = message
        self.id_update_callback = id_update_callback

    @classmethod
    async def send(cls, channel: discord.abc.Messageable, content=None, **kwargs) -> StickyMessage:
        """Send a new sticky message."""
        message = await channel.send(content, **kwargs)
        return cls(message)

    async def update(self, content=None, **kwargs):
        channel = self._message.channel
        history = await channel.history(limit=1).flatten()
        if history[0] != self._message:
            atask(self._message.delete())
            self._message = await channel.send(content, **kwargs)
            if self.id_update_callback:
                self.id_update_callback()
        else:
            atask(self._message.edit(content=content, **kwargs))

    def delete(self):
        atask(self._message.delete())

    @property
    def id(self) -> int:
        return self._message.id
