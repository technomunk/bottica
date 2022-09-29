"""
Facilitation of guild-wide configuration.
"""

from __future__ import annotations

import logging
from os import path
from typing import Annotated, ClassVar, Dict, Type

from bottica.file import GUILD_CONFIG_FOLDER
from bottica.music.song import SongKey
from bottica.util.persist import PERSISTENT, persist, restore

from .validators import Min, MinMax

_logger = logging.getLogger(__name__)


class GuildConfig:
    __instances: ClassVar[Dict[int, GuildConfig]] = {}

    min_repeat_interval: Annotated[MinMax[int], PERSISTENT] = MinMax(32, 1, 1024)
    max_cached_duration: Annotated[Min[int], PERSISTENT] = Min(600, -1)
    announcements: Annotated[dict[int, SongKey], PERSISTENT] = {}
    music_channels: Annotated[list[int], PERSISTENT] = []

    def __init__(self, guild_id: int):
        self.guild_id = guild_id

    @classmethod
    def get(cls: Type[GuildConfig], guild_id: int) -> GuildConfig:
        config = cls.__instances.get(guild_id)
        if config is not None:
            return config

        config = cls(guild_id)
        if path.exists(config.filename):
            restore(config.filename, config)
        persist(config, config.filename)

        cls.__instances[guild_id] = config
        return config

    @property
    def filename(self) -> str:
        return path.join(GUILD_CONFIG_FOLDER, f"{self.guild_id}.json")
