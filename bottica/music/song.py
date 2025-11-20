"""
Define song metadata structure as well as helper collections for managing song queues and sets.
"""

from __future__ import annotations

import csv
import logging
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, astuple, dataclass
from os import path
from random import randrange
from typing import Callable, Deque, Dict, Generator, Iterable, Iterator, Optional, cast
from dataclass_csv import DataclassReader

FILE_ENCODING = "utf8"
EXTENSION = "opus"
FFMPEG_OPTIONS = {"options": "-vn"}

SongKey = tuple[str, str]

_logger = logging.getLogger(__name__)

_LINKS = {"youtube": "https://music.youtube.com/watch?v={.id}"}


# csv.Dialect be like that
# pylint: disable=too-few-public-methods
class SongCSVDialect(csv.Dialect):
    delimiter = ";"
    doublequote = False
    escapechar = "\\"
    lineterminator = "\n"
    quotechar = '"'
    skipinitialspace = True
    quoting = csv.QUOTE_MINIMAL
    strict = True


def keystr(key: SongKey) -> str:
    return " ".join(key)


@dataclass(slots=True)
class SongInfo:
    domain: str
    id: str
    duration: int
    title: str

    @property
    def key(self) -> SongKey:
        return (self.domain, self.id)

    @property
    def filename(self) -> str:
        return f"{self.domain}_{self.id}.{EXTENSION}"

    @property
    def link(self) -> str:
        pretty_link = _LINKS.get(self.domain)
        if pretty_link is None:
            raise NotImplementedError("SongInfo::link", self.domain)

        return pretty_link.format(self)

    @property
    def pretty_link(self) -> str:
        """
        Generate a pretty markdown link that consists of a clickable title.
        """
        return f"[{self.title}]({self.link})"


@contextmanager
def open_song_registry(filename: str) -> Generator[Iterable[SongInfo], None, None]:
    with open(filename, "r", encoding=FILE_ENCODING) as file:
        reader = DataclassReader(file, SongInfo, dialect=cast(str, SongCSVDialect))
        yield reader


class SongRegistry:
    """
    A collection of known songs that can be looked up by song domain+id.
    """

    def __init__(self, filename: str) -> None:
        self._data: Dict[SongKey, tuple[int, str]] = {}
        self._filename = filename
        self._header_written = False
        if path.exists(filename):
            with open_song_registry(filename) as song_registry:
                for song in song_registry:
                    self._data[song.key] = (song.duration, song.title)
            self._header_written = True
        else:
            with open(filename, "w", encoding=FILE_ENCODING) as file:
                assert file

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: SongKey) -> bool:
        return key in self._data

    def __getitem__(self, key: SongKey) -> SongInfo:
        info = self._data[key]
        domain, intradomain_id = key
        return SongInfo(domain, intradomain_id, *info)

    def get(self, key: SongKey) -> Optional[SongInfo]:
        domain, intradomain_id = key
        other_fields = self._data.get(key)
        if other_fields:
            return SongInfo(domain, intradomain_id, *other_fields)
        return None

    def __iter__(self) -> Generator[SongInfo, None, None]:
        return (self[key] for key in self._data)

    def put(self, song: SongInfo) -> None:
        self._data[song.key] = (song.duration, song.title)
        with open(self._filename, "a", encoding=FILE_ENCODING) as file:
            writer = csv.writer(file, dialect=SongCSVDialect)
            if not self._header_written:
                writer.writerow(asdict(song).keys())
                self._header_written = True
            writer.writerow(astuple(song))


class _SongKeyCollection:
    """
    Base class for collections that store song information only by keys
    and retreive full song information using a provided registry.
    """

    def __init__(self, registry: SongRegistry) -> None:
        self._registry = registry

    def _deref(self, song: SongKey) -> SongInfo:
        return self._registry[song]

    def _keys_in(self, file: Iterable[str]) -> Generator[SongKey, None, None]:
        reader = csv.reader(file, dialect=SongCSVDialect)

        try:
            header_row = next(reader)
        except StopIteration:
            # file was empty
            return

        assert list(header_row[:2]) == ["domain", "id"], "invalid song collection backing"

        for row in reader:
            key = row[0], row[1]
            if key in self._registry:
                yield key
            else:
                _logger.warning("%s not found in song registry!", key)


class SongQueue(_SongKeyCollection):
    """
    Sequence of played songs.
    """

    __slots__ = "_registry", "_head", "_tail", "_duration"

    def __init__(self, registry: SongRegistry) -> None:
        super().__init__(registry)
        self._data: Deque[SongKey] = deque()
        self._duration: int = 0

    def __len__(self) -> int:
        return len(self._data)

    def pop(self) -> Optional[SongInfo]:
        """
        Move the next song to the 'head' position if possible.
        Returns the new head.
        """
        if self._data:
            song = self._deref(self._data.popleft())
            self._duration -= song.duration
            return song
        self._duration = 0
        return None

    def pop_random(self) -> Optional[SongInfo]:
        """
        Move a random song from the tail to the 'head' position if possible.
        Returns the new head.
        """
        if self._data:
            idx = randrange(len(self._data))
            song = self._deref(self._data[idx])
            del self._data[idx]
            self._duration -= song.duration
            return song
        self._duration = 0
        return None

    def push(self, song: SongInfo) -> None:
        self._duration += song.duration
        self._data.append(song.key)

    def extend(self, songs: Iterable[SongInfo]) -> None:
        for song in songs:
            self._duration += song.duration
            self._data.append(song.key)

    def clear(self) -> None:
        self._data.clear()
        self._duration = 0

    def __iter__(self) -> Iterator[SongInfo]:
        return map(self._deref, self._data)

    @property
    def duration(self) -> int:
        return self._duration


class SongSet(_SongKeyCollection):
    """
    Set of all songs queued within a guild.
    """

    __slots__ = "_registry", "filename", "_data"

    def __init__(self, registry: SongRegistry, filename: str) -> None:
        super().__init__(registry)
        self.filename = filename
        self._header_written = False
        self._data: set[SongKey] = set()

        if path.exists(filename):
            with open(filename, "r", encoding=FILE_ENCODING) as file:
                self._data = set(self._keys_in(file))
            self._header_written = True
        else:
            with open(filename, "w", encoding=FILE_ENCODING) as file:
                assert file

    def add(self, song: SongInfo) -> bool:
        if song.key in self._data:
            return False
        self._data.add(song.key)
        with open(self.filename, "a", encoding=FILE_ENCODING) as file:
            writer = csv.writer(file, dialect=SongCSVDialect)
            if not self._header_written:
                writer.writerow(["domain", "id"])
                self._header_written = True
            writer.writerow(song.key)
        return True

    def select_random(
        self,
        *,
        block_list: Iterable[SongInfo] | None = None,
        allow_predicate: Callable[[SongInfo], bool] | None = None,
    ) -> Optional[SongInfo]:
        if block_list:
            if isinstance(block_list, SongQueue):
                # Known hotpath optimization
                # pylint: disable=protected-access
                block_set = set(block_list._data)
            else:
                block_set = set(song.key for song in block_list)

            if allow_predicate:
                keys = list(
                    key
                    for key in self._data
                    if key not in block_set and allow_predicate(self._deref(key))
                )
            else:
                keys = list(key for key in self._data if key not in block_set)

        else:
            if allow_predicate:
                keys = list(key for key in self._data if allow_predicate(self._deref(key)))
            else:
                keys = list(key for key in self._data)

        if keys:
            idx = randrange(len(keys))
            return self._deref(keys[idx])
        return None

    def __contains__(self, song: SongInfo) -> bool:
        return song.key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Generator[SongInfo, None, None]:
        return (self._deref(key) for key in self._data)
