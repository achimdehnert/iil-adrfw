.PHONY: test lint types

# Lokal laeuft die Test-Umgebung in .venv (make setup); in CI installiert der
# Publish-Workflow per `pip install -e ".[dev]"` in den Runner-Python und ruft
# danach `make test` — dort gibt es kein .venv. Der Publish-Lauf fuer 0.9.0
# (2026-09-24, Run 35970040795) scheiterte genau daran: "make: .venv/bin/python:
# No such file or directory". Fallback auf python3, wenn kein .venv vorhanden ist.
PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

test:
	$(PY) -m pytest examples/

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
