.PHONY: test lint types

test:
	python3 -m pytest examples/

lint:
	python3 -m ruff check .

types:
	python3 -m mypy src/iil_adrfw
