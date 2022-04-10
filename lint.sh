poetry run flake8 bottica/
poetry run mypy --namespace-packages bottica/
poetry run pylint bottica/
poetry run black --check bottica/
