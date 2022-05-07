poetry run flake8 bottica/
poetry run mypy --config-file tox.ini bottica/
poetry run pylint bottica/
poetry run black --check bottica/
