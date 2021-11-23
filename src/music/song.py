from __future__ import annotations

import logging
from collections import deque
from os import path
from random import randrange
from typing import Deque, Dict, Generator, Iterable, Optional, Set, Tuple, cast

FILE_ENCODING = "utf8"

_logger = logging.getLogger(__name__)

SongKey = Tuple[str, str]


def keystr(key: SongKey) -> str:
    return " ".join(key)


class SongInfo:
    __slots__ = ("domain", "id", "ext", "duration", "title")

    def __init__(
        self,
        domain: str,
        id: str,
        ext: str,
        duration: int,
        title: str,
    ) -> None:
        self.domain = domain
        self.id = id
        self.ext = ext
        self.duration = duration
        self.title = title

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

    @classmethod
    def from_line(cls, line: str) -> SongInfo:
        [domain, id, ext, dur, title] = line.strip().split(maxsplit=4)
        duration = int(dur)
        return cls(domain, id, ext, duration, title)

    def to_line(self) -> str:
        return " ".join(
            (
                self.domain,
                self.id,
                self.ext,
                repr(self.duration),
                self.title,
            )
        )


class SongRegistry:
    """
    A collection of known songs that can be looked up by song domain+id.
    """

    def __init__(self, filename: str) -> None:
        self._data: Dict[SongKey, Tuple[str, int, str]] = {}
        self._filename = filename
        if path.exists(filename):
            with open(filename, "r", encoding=FILE_ENCODING) as file:
                for line in file:
                    song = SongInfo.from_line(line)
                    self._data[song.key] = (song.ext, song.duration, song.title)
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
            file.write(song.to_line())
            file.write("\n")


class _SongKeyCollection:
    """
    Base class for collections that store song information only by keys
    and retreive full song information using a provided registry.
    """

    def __init__(self, registry: SongRegistry) -> None:
        self._registry = registry

    def _deref(self, song: SongKey) -> SongInfo:
        return self._registry[song]

    def _keys_in(self, lines: Iterable[str]) -> Generator[SongKey, None, None]:
        for line in lines:
            key = cast(SongKey, tuple(line.strip().split(maxsplit=1)))
            if key in self._registry:
                yield key
            else:
                _logger.warning("%s not found in song registry!", key)


class SongQueue(_SongKeyCollection):
    """
    Sequence of played songs.
    """

    def __init__(self, registry: SongRegistry) -> None:
        super().__init__(registry)
        self._head: Optional[SongKey] = None
        self._tail: Deque[SongKey] = deque()
        self.duration: int = 0

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
                self.duration -= self._deref(self._head).duration
            self._head = self._tail.popleft()
        else:
            self.duration = 0
            self._head = None
        return self.head

    def pop_random(self) -> Optional[SongInfo]:
        """
        Move a random song from the tail to the 'head' position if possible.
        Returns the new head.
        """
        if self._tail:
            if self._head is not None:
                self.duration -= self._deref(self._head).duration
            idx = randrange(len(self._tail))
            self._head = self._tail[idx]
            del self._tail[idx]
        else:
            self.duration = 0
            self._head = None
        return self.head

    def push(self, song: SongInfo) -> None:
        self.duration += song.duration
        self._tail.append(song.key)

    def extend(self, it: Iterable[SongInfo]) -> None:
        for song in it:
            self._tail.append(song.key)
            self.duration += song.duration

    def clear(self) -> None:
        self._head = None
        self._tail.clear()
        self.duration = 0


class SongSet(_SongKeyCollection):
    """
    Set of all songs queued within a guild.
    """

    def __init__(self, registry: SongRegistry, filename: str) -> None:
        super().__init__(registry)
        self.filename = filename
        self._data: Set[SongKey] = set()

        if path.exists(filename):
            with open(filename, "r", encoding=FILE_ENCODING) as file:
                self._data = set(self._keys_in(file))
        else:
            with open(filename, "w", encoding=FILE_ENCODING) as file:
                assert file

    def add(self, song: SongInfo) -> None:
        if song.key in self._data:
            return
        self._data.add(song.key)
        with open(self.filename, "a", encoding=FILE_ENCODING) as file:
            file.write(keystr(song.key))
            file.write("\n")

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Generator[SongInfo, None, None]:
        return (self._registry[key] for key in self._data)
