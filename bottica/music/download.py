"""Song data download utilities"""
from functools import partial
from logging import getLogger
from os import path
from typing import Iterable, NewType, Optional, cast

from yt_dlp import YoutubeDL  # type: ignore

from bottica.file import AUDIO_FOLDER, DATA_FOLDER
from bottica.infrastructure import file
from bottica.infrastructure.error import atask, event_loop
from bottica.infrastructure.friendly_error import FriendlyError
from bottica.music.error import InvalidURLError
from bottica.music.normalize import normalize_song

from .song import EXTENSION as SONG_EXTENSION
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
        "no_warnings": True,
        "nopart": True,
    }
)


class DownloadError(FriendlyError):
    def __init__(self):
        super().__init__("Sorry, I couldn't download provided url :(")


async def download_song(song: SongInfo | ReqInfo, keep: bool) -> str:
    """
    Download provided song data. Returns filename of the streamed file.
    If cache is True - once the song is downloaded it will be loud-normalized, compressed and saved to song.filename.
    """
    if isinstance(song, dict):
        req = song
        song = cast(SongInfo, _extract_song_info(req))
    else:
        req = await _get_info(song)

    if not req:
        raise InvalidURLError()

    task = _download_and_normalize if keep else _download
    atask(task(req))

    filename = path.join(AUDIO_FOLDER, song.filename.replace(f".{SONG_EXTENSION}", f".{req.get('ext', '')}"))
    await file.wait_until_available(filename, 2)

    return filename


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


async def _get_info(song: SongInfo) -> ReqInfo:
    return await event_loop.run_in_executor(
        None,
        partial(
            _loader.extract_info,
            song.link,
            download=False,
        ),
    )


async def _download_and_normalize(req: ReqInfo):
    filename = await _download(req)
    await normalize_song(filename)


async def _download(req: ReqInfo) -> str:
    ie_info = await event_loop.run_in_executor(
        None,
        partial(
            _loader.process_ie_result,
            req,
            download=True,
        ),
    )

    if not ie_info:
        raise DownloadError()

    return ie_info["requested_downloads"][0]["filepath"]
    # # fmt: off
    # command = [
    #     "ffmpeg",
    #     "-v", "error",
    #     "-y",
    #     "-nostdin",
    #     "-vn",  # no video
    #     "-sn",  # no audio
    #     "-i", url,
    #     "-map_chapters", "-1",
    #     "-map_metadata", "-1",
    #     filename,
    # ]
    # # fmt: on
    # process = await create_subprocess_shell(
    #     cmd.join(command),
    #     stdin=subprocess.DEVNULL,
    #     stderr=subprocess.PIPE,
    #     stdout=subprocess.DEVNULL,
    # )

    # error_code = await process.wait()
    # if error_code:
    #     _, output = await process.communicate()
    #     _logger.error(output.decode())
    #     raise DownloadError()
