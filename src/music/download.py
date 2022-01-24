from asyncio import BaseEventLoop
from logging import getLogger
from typing import Tuple

from yt_dlp import YoutubeDL

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
        return _extract_song_info(info)


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
    domain, id = extract_key(info)
    return SongInfo(domain, id, info["ext"], info["duration"], info["title"])
