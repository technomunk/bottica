"""Unit tests for persist module"""
from pathlib import Path

from bottica.infrastructure.config import GuildConfig
from bottica.util.persist import persist, restore


def test_persist_guild_config(tmp_path: Path) -> None:
    filename = tmp_path / "test.json"

    original = GuildConfig(0)
    original.announcements = {123: ("a", "b")}

    persist(original, filename)

    loaded = GuildConfig(0)
    restore(filename, loaded)

    assert original.announcements == loaded.announcements
