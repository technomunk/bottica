"""
Facilitation of guild-wide configuration.
"""

from __future__ import annotations

import json
import logging
from os import path
from typing import ClassVar, Dict, Type, TypeVar

from file import GUILD_CONFIG_FOLDER

from .validators import MinMax, ValidationError

VarT = TypeVar("VarT")

_logger = logging.getLogger(__name__)


class GuildConfig:
    __instances: ClassVar[Dict[int, GuildConfig]] = {}
    __fields: ClassVar = ["min_repeat_interval"]

    min_repeat_interval = MinMax(32, 1, 1024)

    def __new__(cls: Type[GuildConfig], guild_id: int) -> GuildConfig:
        if config := cls.__instances.get(guild_id):
            return config

        _logger.debug("allocating new guild config")
        return super().__new__(cls)

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        if path.exists(self.filename):
            self.load()

        self.save()

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
