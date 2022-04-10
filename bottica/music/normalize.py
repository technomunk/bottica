"""Loudness-normalization utility."""
import logging
from os import path, remove
from os.path import splitext

import ffmpeg_normalize  # type: ignore
from ffmpeg_normalize import FFmpegNormalize, MediaFile

from bottica.file import AUDIO_FOLDER

from .song import EXTENSION

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
    "output_format": EXTENSION,
}
_default_config = FFmpegNormalize(**DEFAULT_NORMALIZATION_CONFIG)


def normalize_song(
    src_file: str,
    config: FFmpegNormalize = _default_config,
    keep_old_file: bool = False,
):
    filename = path.basename(src_file)
    name, _ = splitext(filename)
    dst_file = path.join(AUDIO_FOLDER, f"{name}.{config.output_format}")

    if path.exists(dst_file):
        _logger.warning("Song already normalized: %s", dst_file)
        return

    _logger.debug("Normalizing %s => %s", src_file, dst_file)
    normalization = MediaFile(config, src_file, dst_file)
    normalization.run_normalization()

    if not keep_old_file:
        try:
            remove(src_file)
        except FileNotFoundError:
            pass
