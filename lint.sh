poetry run flake8 src/
poetry run mypy --namespace-packages src/
poetry run pylint src/
poetry run black --check src/
