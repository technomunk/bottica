# Bottica

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting & code analysis](https://github.com/technomunk/bottica/actions/workflows/lint.yml/badge.svg)](https://github.com/technomunk/bottica/actions/workflows/lint.yml)

A personal music-playing discord bot project.

## Using

The bot ran by [Technomunk](https://github.com/technomunk) is personal and thus can only be invited
by them. To interact with the bot on the server send to any chat a message beginning with `b.`.
Start by using `b.help` which will print all available commands.

## Installing

- Get [python 3.10](https://www.python.org/downloads/).
- Get [poetry](https://python-poetry.org/docs/#installation).
- Make sure [poetry uses python 3.10](https://python-poetry.org/docs/managing-environments/#switching-between-environments).
- Run `poetry install`
- Get bot token from discord `https://discord.com/developers/applications/<app_id>/bot` and save it to `config.toml`

## Running

```sh
poetry run python3 src/manage.py run
```

## Contributing

- Submit issues with wished functionality or problems encountered during use
- Fork the repo and make an upstream PR with your own changes
  + Install dev requirements `pip install -r requirements-dev.txt`
  + Run analysis tools:
    * `mypy --namespace-packages src/`
    * `pylint src/`
    * `flake8 src/`
    * `black --check src/`
  + Resolve any issues you see.
