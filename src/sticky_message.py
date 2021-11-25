from __future__ import annotations

from typing import Optional, Tuple

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
        """Send a new sticky message."""
        message = await channel.send(content, **kwargs)
        return cls(message)

    @classmethod
    async def from_ids(cls, ids: Tuple[int, int], guild: discord.Guild) -> Optional[StickyMessage]:
        channels = await guild.fetch_channels()
        for channel in channels:
            if channel.id == ids[0]:
                message = await channel.fetch_message(ids[1])
                return cls(message)

        return None

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

    @property
    def ids(self) -> Tuple[int, int]:
        return self._message.channel.id, self._message.id
