"""Loudness-normalization utility."""
# from asyncio import create_subprocess_shell
import asyncio
import json
import logging
import os
import sys
from asyncio import create_subprocess_shell, subprocess
from os import path
from typing import Any

from bottica.file import AUDIO_FOLDER
from bottica.infrastructure import cmd
from bottica.music.song import EXTENSION as SONG_EXTENSION

_logger = logging.getLogger(__name__)


def stream_normalize_ffmpeg_args(
    *,
    loudness_level: float = -15,
    loudness_range: float = 7,
    true_peak: float = -2,
) -> str:
    """Get ffmpeg options that will make sure it loud-normalizes a stream"""
    args = [
        "-af",
        _loudnorm_options(
            i=loudness_level,
            lra=loudness_range,
            true_peak=true_peak,
        ),
    ]
    return cmd.join(args)


async def normalize_song(
    src_file: str,
    *,
    loudness_level: float = -15,
    loudness_range: float = 7,
    true_peak: float = -2,
    keep_old_file: bool = False,
):
    filename = path.basename(src_file)
    name, _ = path.splitext(filename)
    tmp_file = path.join(AUDIO_FOLDER, f"{name}.tmp")
    dst_file = path.join(AUDIO_FOLDER, f"{name}.{SONG_EXTENSION}")

    if path.exists(tmp_file) or path.exists(dst_file):
        _logger.warning("Song already normalized: %s", dst_file)
        return

    _logger.debug("Normalizing %s => %s", src_file, dst_file)
    await _run_normalization(
        src_file,
        tmp_file,
        loudness_level=loudness_level,
        loudness_range=loudness_range,
        true_peak=true_peak,
    )

    os.rename(tmp_file, dst_file)

    if not keep_old_file:
        try:
            os.remove(src_file)
        except FileNotFoundError:
            pass


async def _run_normalization(
    src_file: str,
    dst_file: str,
    *,
    loudness_level: float,
    loudness_range: float,
    true_peak: float,
):
    loudnorm_args = {
        "i": loudness_level,
        "lra": loudness_range,
        "tp": true_peak,
    }
    output = await _run_first_pass(src_file, loudnorm_args)
    for key in output:
        if key.startswith("measured"):
            loudnorm_args[key] = output[key]

    await _run_second_pass(src_file, dst_file, loudnorm_args)


async def _run_first_pass(src_file: str, loudnorm_args: dict) -> dict[str, Any]:
    # fmt: off
    pass_cmd = [
        "ffmpeg",
        "-hide_banner",  # reduce verbosity somewhat
        "-nostdin",
        "-vn",
        "-sn",
        "-i", src_file,
        "-af",
        _loudnorm_options(print_format="json", **loudnorm_args),
        "-f", "null",  # convert output to nothing
        "-",
    ]
    # fmt: on

    process = await create_subprocess_shell(
        cmd.join(pass_cmd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    code = await process.wait()
    _, output = await process.communicate()
    if code != 0:
        print(output)
        raise RuntimeWarning(f"ffmpeg return error code: {code}")

    return _read_output(output.decode())


async def _run_second_pass(src_file: str, dst_file: str, loudnorm_args: dict):
    # fmt: off
    pass_cmd = [
        "ffmpeg",
        "-nostdin",
        "-v", "0",
        "-y",
        "-vn",
        "-sn",
        "-i", src_file,
        "-af",
        _loudnorm_options(**loudnorm_args),
        "-map_chapters", "-1",
        "-map_metadata", "-1",
        "-c:a", "libopus",
        "-b:a", "96k",
        "-ar", "48000",
        "-f", "opus",
        "-ac", "2",
        dst_file,
    ]
    # fmt: on
    process = await create_subprocess_shell(
        cmd.join(pass_cmd),
        stdin=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    await process.wait()


def _loudnorm_options(**kwargs: Any) -> str:
    return "loudnorm=" + ":".join(f"{k}={v}" for k, v in kwargs.items())


def _read_output(output: str) -> dict:
    idx = output.find("[Parsed_loudnorm")
    if idx == -1:
        _logger.error(output)
        raise RuntimeError("Could not process first pass output")
    idx = output.find("{", idx)
    if idx == -1:
        _logger.error(output)
        raise RuntimeError("Could not process first pass output")
    return json.loads(output[idx:])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("python3", __name__, "INPUT")
        sys.exit()

    asyncio.run(normalize_song(sys.argv[1], keep_old_file=True))
