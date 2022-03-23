"""Loudness-normalization utility."""
import logging
from os import remove
from os.path import splitext

import ffmpeg_normalize  # type: ignore
from ffmpeg_normalize import FFmpegNormalize, MediaFile

from .file import AUDIO_FOLDER
from .song import SongInfo

_logger = logging.getLogger(__name__)

# FFMEG is too verbose and pre-initializes its logger
# pylint: disable=protected-access
ffmpeg_normalize._media_file.logger.setLevel(logging.ERROR)

DEFAULT_NORMALIZATION_CONFIG = {
    "target_level": -18,
    "audio_codec": "libopus",
    "video_disable": True,
    "subtitle_disable": True,
    "metadata_disable": True,
    "chapters_disable": True,
    "output_format": "opus",
}
_default_config = FFmpegNormalize(**DEFAULT_NORMALIZATION_CONFIG)


def normalize_song(
    song: SongInfo,
    config: FFmpegNormalize = _default_config,
    keep_old_file: bool = False,
):
    ext = "." + config.output_format
    src_file = AUDIO_FOLDER + song.filename
    filename, _ = splitext(src_file)
    dst_file = filename + ext

    _logger.debug("Normalizing %s => %s", src_file, dst_file)
    normalization = MediaFile(config, src_file, dst_file)
    normalization.run_normalization()

    if not keep_old_file:
        remove(src_file)

    song.ext = config.output_format
