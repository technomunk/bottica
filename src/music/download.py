"""Song data download utilities"""
from functools import partial
from logging import getLogger
from os import path
from typing import Iterable, NewType, Optional

from yt_dlp import YoutubeDL  # type: ignore

from file import AUDIO_FOLDER, DATA_FOLDER
from infrastructure.error import event_loop
from music.normalize import normalize_song

from .song import SongInfo

ReqInfo = NewType("ReqInfo", dict)

_logger = getLogger(__name__)

_loader = YoutubeDL(
    {
        "format": "bestaudio",
        "outtmpl": path.join(AUDIO_FOLDER, "%(extractor)s_%(id)s.%(ext)s"),
        "cachedir": path.join(DATA_FOLDER, "dlcache"),
        "ignoreerrors": True,
        "cookiefile": path.join(DATA_FOLDER, "cookies.txt"),
        "quiet": True,
        "noplaylist": True,
    }
)


async def streamable_url(song: SongInfo, cache: bool) -> str:
    info = await event_loop.run_in_executor(
        None,
        partial(
            _loader.extract_info,
            song.link,
            download=False,
        ),
    )

    if cache:
        # Run the download completely asynchronously without blocking
        task = event_loop.run_in_executor(None, partial(_download_and_normalize, info))
        event_loop.create_task(task)

    return info.get("url", "")


async def process_request(query: str) -> Iterable[SongInfo]:
    """Process provided query and get the songs it requests in order."""
    req_info = await event_loop.run_in_executor(
        None,
        partial(
            _loader.extract_info,
            query,
            download=False,
            process=False,
        ),
    )

    req_type = req_info.get("_type", "video")

    if req_type == "playlist":
        return filter(None, (_extract_song_info(req) for req in req_info["entries"]))

    song_info = _extract_song_info(req_info)
    return [song_info] if song_info else []


def _extract_song_info(info: ReqInfo) -> Optional[SongInfo]:
    info_type = info.get("_type", "video")
    if info_type not in ("video", "url"):
        return None

    domain = info.get("ie_key", info.get("extractor_key")).lower()
    return SongInfo(
        domain,
        id=info["id"],
        duration=info["duration"],
        title=info["title"],
    )


def _download_and_normalize(info: ReqInfo) -> None:
    _loader.process_ie_result(info, download=True)
    song = _extract_song_info(info)
    if song is None:
        _logger.error("could not extract song info for %s", info.get("id"))
        return

    normalize_song(song)
