"""Song data download utilities"""
from functools import partial
from logging import getLogger
from os import path
from typing import Iterable, NewType, Optional

from yt_dlp import YoutubeDL  # type: ignore

from bottica.file import AUDIO_FOLDER, DATA_FOLDER
from bottica.infrastructure.error import atask, event_loop
from bottica.music.error import InvalidURLError
from bottica.music.normalize import normalize_song

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
        "noprogress": True,
    }
)


async def streamable_url(song: SongInfo, allow_caching: bool) -> str:
    info = await event_loop.run_in_executor(
        None,
        partial(
            _loader.extract_info,
            song.link,
            download=False,
        ),
    )

    if allow_caching:
        # Run the download completely asynchronously without blocking
        atask(_download_and_normalize(info))

    return info.get("url", "")


async def download_and_normalize(song: SongInfo):
    info = await event_loop.run_in_executor(
        None,
        partial(
            _loader.extract_info,
            song.link,
            download=False,
        ),
    )
    await _download_and_normalize(info)


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

    if req_info is None:
        raise InvalidURLError()

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
        duration=int(info["duration"]),
        title=info["title"],
    )


async def _download_and_normalize(info: ReqInfo) -> None:
    ie_info = await event_loop.run_in_executor(
        None,
        partial(
            _loader.process_ie_result,
            info,
            download=True,
        ),
    )
    filename = ie_info["requested_downloads"][0]["filepath"]

    if not path.exists(filename):
        _logger.error("Could not download %s", filename)
        return

    await normalize_song(filename)
