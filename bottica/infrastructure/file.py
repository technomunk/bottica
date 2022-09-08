"""Extra utilities for file interactions."""


import asyncio
from os import path


async def wait_until_available(
    filename: str,
    timeout: float = 0,
    *,
    poll_period: float = 0.2,
) -> None:
    """Wait for"""
    elapsed_time = 0.0
    while timeout > 0 and elapsed_time < timeout:
        try:
            if path.getsize(filename):
                return
        except OSError:
            await asyncio.sleep(poll_period)
            elapsed_time += poll_period
    raise TimeoutError()
