"""Song data download utilities"""
from asyncio import BaseEventLoop
from logging import getLogger
from os import path
from time import sleep
from typing import Tuple

from yt_dlp import YoutubeDL  # type: ignore

from .file import AUDIO_FOLDER, DATA_FOLDER
from .song import SongInfo

_logger = getLogger(__name__)

_DEFAULT_CONFIG = {
    "format": "bestaudio",
    "outtmpl": AUDIO_FOLDER + "%(extractor)s_%(id)s.%(ext)s",
    "cachedir": DATA_FOLDER + "dlcache",
    "ignoreerrors": True,
    "cookiefile": DATA_FOLDER + "cookies.txt",
    "quiet": True,
    "noplaylist": True,
}


class Downloader:
    # I know the config is not mutated by the method and I prefer non-optional arguments
    # pylint: disable=dangerous-default-value
    def __init__(self, loop: BaseEventLoop, config: dict = _DEFAULT_CONFIG) -> None:
        self._loader = YoutubeDL(config)
        self.loop = loop

    async def get_info(self, url: str) -> dict:
        return await self.loop.run_in_executor(
            None,
            lambda: self._loader.extract_info(url, download=False, process=False),
        )

    async def download(self, info: dict) -> SongInfo:
        info = await self.loop.run_in_executor(None, lambda: self._loader.process_ie_result(info))
        _logger.debug("download complete")
        song_info = _extract_song_info(info)
        _ensure_exists(AUDIO_FOLDER + song_info.filename)
        return song_info


def extract_key(info: dict) -> Tuple[str, str]:
    """
    Generate key for a given song.
    """
    info_type = info.get("_type", "video")
    if info_type not in ("video", "url"):
        raise NotImplementedError(f"genname(info['_type']: '{info_type}')")
    domain = info.get("ie_key", info.get("extractor_key")).lower()
    return (domain, info["id"])


def _extract_song_info(info: dict) -> SongInfo:
    domain, intradomain_id = extract_key(info)
    return SongInfo(domain, intradomain_id, info["ext"], info["duration"], info["title"])


def _ensure_exists(filename: str, timeout: float = 2, poll_rate: float = 0.2) -> None:
    """
    Make sure the provided file exists.

    Done because ytdlp does not always synchronize file writes.
    """
    if path.exists(filename):
        return

    total = 0.0
    while total < timeout:
        total += poll_rate
        sleep(poll_rate)

        if path.exists(filename):
            return

    raise RuntimeError(filename, "does not exist")
