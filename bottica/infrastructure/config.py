"""
Facilitation of guild-wide configuration.
"""

from __future__ import annotations

import json
import logging
from os import path
from typing import ClassVar, Dict, Type

from bottica.file import GUILD_CONFIG_FOLDER
from bottica.music.song import SongKey

from .converters import DeferredConverter
from .validators import Min, MinMax, ValidationError

_logger = logging.getLogger(__name__)


def _to_announcements(source: dict) -> Dict[int, SongKey]:
    return {int(key): (str(val[0]), str(val[1])) for key, val in source.items()}


class GuildConfig:
    __instances: ClassVar[Dict[int, GuildConfig]] = {}
    __fields: ClassVar = ["min_repeat_interval", "max_cached_duration", "announcements"]

    min_repeat_interval: MinMax[int] = MinMax(32, 1, 1024)
    max_cached_duration: Min[int] = Min(600, -1)
    announcements = DeferredConverter(_to_announcements, dict)

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id

    @classmethod
    def get(cls: Type[GuildConfig], guild_id: int) -> GuildConfig:
        config = cls.__instances.get(guild_id)
        if config is not None:
            return config

        config = cls(guild_id)
        if path.exists(config.filename):
            config.load()
        config.save()

        cls.__instances[guild_id] = config
        return config

    def load(self) -> None:
        """Load values from a file."""
        with open(self.filename, "r", encoding="utf8") as json_file:
            config: dict = json.load(json_file)

        for field in self.__fields:
            try:
                value = config[field]
                setattr(self, field, value)
            except ValidationError:
                _logger.warning(
                    "validation error when loading '%s' for guild_id(%i)",
                    field,
                    self.guild_id,
                )
            except KeyError:
                _logger.warning(
                    "'%s' field is not in loaded config for guild_id(%i), defaulting",
                    field,
                    self.guild_id,
                )

    def save(self) -> None:
        """Save the current values to a file."""
        config: dict = {}
        for field in self.__fields:
            config[field] = getattr(self, field)

        with open(self.filename, "w", encoding="utf8") as json_file:
            json.dump(config, json_file)

    @property
    def filename(self) -> str:
        return path.join(GUILD_CONFIG_FOLDER, f"{self.guild_id}.json")
