# Bottica data management tooling.
# Use caution when using while Bottica is running.

from os import abort, listdir, stat
from typing import Dict, Literal, Optional

import click

from music.file import DATA_FOLDER


MultiplierType = Literal["K", "M", "G"]
MULTIPLIERS: Dict[MultiplierType, int] = {
    "K": 1 << 10,
    "M": 1 << 20,
    "G": 1 << 30,
}


@click.group()
@click.pass_context
def cli():
    pass


@cli.command()
@click.argument("count", type=int, min=1)
@click.argument("unit", type=Optional[MultiplierType], required=False, default=None)
def prune(count: int, unit: Optional[MultiplierType]):
    """Unlink and remove files larger than provided size."""
    multiplier = MULTIPLIERS.get(unit, 1) if unit else 1
    min_size = count * multiplier
    # TODO: collect linked files and only iterate through them
    files_to_remove = [file for file in listdir(DATA_FOLDER) if stat(file).st_size >= min_size]
    click.confirm(
        f"Found {len(files_to_remove)} files larger than {count}{unit}. Delete them?",
        abort=True,
    )
    # TODO: unlink files
    # TODO: remove files
    raise NotImplementedError()


@cli.command()
def clean():
    """Remove any data not linked to Bottica."""
    raise NotImplementedError()
