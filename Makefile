.PHONY: test lint types

test:
	.venv/bin/python -m pytest examples/

lint:
	python3 -m ruff check .

types:
	python3 -m mypy src/iil_adrfw

# Fleet-Standard-Einstieg (pkg-agents-v1, platform #2075 K2): make setup && make test
setup:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e .
	.venv/bin/pip install pytest
