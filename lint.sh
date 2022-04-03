flake8 src/
mypy --namespace-packages src/
pylint src/
black --check src/
