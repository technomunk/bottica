from __future__ import annotations

import csv
import logging
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from os import path
from random import randrange
from typing import Deque, Dict, Generator, Iterable, Optional, Set, Tuple, cast

from attr import asdict, astuple
from dataclass_csv import DataclassReader

FILE_ENCODING = "utf8"

SongKey = Tuple[str, str]

_logger = logging.getLogger(__name__)


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
    ext: str
    duration: int
    title: str

    @property
    def key(self) -> SongKey:
        return (self.domain, self.id)

    @property
    def filename(self) -> str:
        return f"{self.domain}_{self.id}.{self.ext}"

    @property
    def link(self) -> str:
        if self.domain != "youtube":
            raise NotImplementedError("SongInfo::link(domain != youtube)")
        return f"https://www.{self.domain}.com/watch?v={self.id}"

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
        self._data: Dict[SongKey, Tuple[str, int, str]] = {}
        self._filename = filename
        self._header_written = False
        if path.exists(filename):
            with open_song_registry(filename) as song_registry:
                for song in song_registry:
                    self._data[song.key] = (song.ext, song.duration, song.title)
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
        domain, id = key
        return SongInfo(domain, id, *info)

    def get(self, key: SongKey) -> Optional[SongInfo]:
        domain, id = key
        ext_title = self._data.get(key)
        if ext_title:
            return SongInfo(domain, id, *ext_title)
        return None

    def __iter__(self) -> Generator[SongInfo, None, None]:
        return (self[key] for key in self._data)

    def put(self, song: SongInfo) -> None:
        self._data[song.key] = (song.ext, song.duration, song.title)
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
        header_row = next(reader)

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
        self._head: Optional[SongKey] = None
        self._tail: Deque[SongKey] = deque()
        self._duration: int = 0

    def __len__(self) -> int:
        return len(self._tail) + int(self._head is not None)

    @property
    def head(self) -> Optional[SongInfo]:
        return self._deref(self._head) if self._head is not None else None

    def pop(self) -> Optional[SongInfo]:
        """
        Move the next song to the 'head' position if possible.
        Returns the new head.
        """
        if self._tail:
            if self._head is not None:
                self._duration -= self._deref(self._head).duration
            self._head = self._tail.popleft()
        else:
            self._duration = 0
            self._head = None
        return self.head

    def pop_random(self) -> Optional[SongInfo]:
        """
        Move a random song from the tail to the 'head' position if possible.
        Returns the new head.
        """
        if self._tail:
            if self._head is not None:
                self._duration -= self._deref(self._head).duration
            idx = randrange(len(self._tail))
            self._head = self._tail[idx]
            del self._tail[idx]
        else:
            self._duration = 0
            self._head = None
        return self.head

    def push(self, song: SongInfo) -> None:
        self._duration += song.duration
        self._tail.append(song.key)

    def extend(self, it: Iterable[SongInfo]) -> None:
        for song in it:
            self._tail.append(song.key)
            self._duration += song.duration

    def clear(self) -> None:
        self._head = None
        self._tail.clear()
        self._duration = 0

    def __iter__(self) -> Generator[SongInfo, None, None]:
        if self._head is not None:
            yield self._deref(self._head)
        for key in self._tail:
            yield self._deref(key)

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
        self._data: Set[SongKey] = set()

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

    def __contains__(self, song: SongInfo) -> bool:
        return song.key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Generator[SongInfo, None, None]:
        return (self._deref(key) for key in self._data)
