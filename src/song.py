from __future__ import annotations

import logging
from collections import deque
from os import path
from random import randrange
from typing import Deque, Dict, Generator, Iterable, Optional, Tuple

logger = logging.Logger(__name__)


class BriefSongInfo:
    __slots__ = ("domain", "id", "ext", "duration")

    def __init__(self, domain: str, id: str, ext: str, duration: int) -> None:
        self.domain = domain
        self.id = id
        self.ext = ext
        self.duration = duration

    @property
    def key(self) -> Tuple[str, str]:
        return (self.domain, self.id)

    @property
    def filename(self) -> str:
        return f"{self.domain}_{self.id}.{self.ext}"

    @property
    def link(self) -> str:
        if self.domain != "youtube":
            raise NotImplementedError("SongInfo::link(domain != youtube)")
        return f"https://www.{self.domain}.com/watch?v={self.id}"


class SongInfo(BriefSongInfo):
    __slots__ = ("title")

    def __init__(
        self,
        domain: str,
        id: str,
        ext: str,
        duration: int,
        title: str,
    ) -> None:
        super().__init__(domain, id, ext, duration)
        self.title = title

    @property
    def pretty_link(self) -> str:
        """
        Generate a pretty markdown link that consists of a clickable title.
        """
        return f"[{self.title}]({self.link})"

    @property
    def brief(self) -> BriefSongInfo:
        return BriefSongInfo(self.domain, self.id, self.ext, self.duration)

    @classmethod
    def from_line(cls, line: str) -> SongInfo:
        [domain, id, ext, dur, title] = line.split(maxsplit=4)
        duration = int(dur)
        return cls(domain, id, ext, duration, title)

    def to_line(self) -> str:
        return " ".join((
            self.domain,
            self.id,
            self.ext,
            repr(self.duration),
            self.title,
        ))


class SongRegistry:
    """
    A collection of known songs that can be looked up by song domain+id.
    """
    def __init__(self, filename: str) -> None:
        self._data: Dict[Tuple[str, str], Tuple[str, int, str]] = {}
        self._filename = filename
        if path.exists(filename):
            with open(filename, "r", encoding="utf8") as file:
                for line in file:
                    song = SongInfo.from_line(line)
                    self._data[song.key] = (song.ext, song.duration, song.title)
        else:
            with open(filename, "w", encoding="utf8") as file:
                assert file

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: Tuple[str, str]) -> bool:
        return key in self._data

    def __getitem__(self, key: Tuple[str, str]) -> SongInfo:
        info = self._data[key]
        domain, id = key
        return SongInfo(domain, id, *info)

    def get(self, key: Tuple[str, str]) -> Optional[SongInfo]:
        domain, id = key
        ext_title = self._data.get(key)
        if ext_title:
            return SongInfo(domain, id, *ext_title)
        return None

    def __iter__(self) -> Generator[SongInfo, None, None]:
        return (self[key] for key in self._data)

    def put(self, song: SongInfo) -> None:
        logger.debug(f'putting {song}')
        self._data[song.key] = (song.ext, song.duration, song.title)
        with open(self._filename, "a", encoding="utf8") as file:
            file.write(song.to_line())
            file.write("\n")


class SongQueue:
    """
    Sequence of played songs.
    """
    def __init__(self) -> None:
        self.head: Optional[BriefSongInfo] = None
        self.tail: Deque[BriefSongInfo] = deque()
        self.duration: int = 0

    def __len__(self) -> int:
        return len(self.tail) + int(self.head is not None)

    def pop(self) -> Optional[BriefSongInfo]:
        """
        Move the next song to the 'head' position if possible.
        Returns the new head.
        """
        if self.tail:
            if self.head is not None:
                self.duration -= self.head.duration
            self.head = self.tail.popleft()
        else:
            self.duration = 0
            self.head = None
        return self.head

    def pop_random(self) -> Optional[BriefSongInfo]:
        """
        Move a random song from the tail to the 'head' position if possible.
        Returns the new head.
        """
        if self.tail:
            if self.head is not None:
                self.duration -= self.head.duration
            idx = randrange(len(self.tail))
            self.head = self.tail[idx]
            del self.tail[idx]
        else:
            self.duration = 0
            self.head = None
        return self.head

    def push(self, song: BriefSongInfo) -> None:
        self.duration += song.duration
        self.tail.append(song)

    def extend(self, it: Iterable[BriefSongInfo]) -> None:
        oldlen = len(self.tail)
        self.tail.extend(it)
        self.duration += sum(song.duration for song in self.tail[oldlen:])

    def clear(self) -> None:
        self.head = None
        self.tail.clear()
        self.duration = 0
