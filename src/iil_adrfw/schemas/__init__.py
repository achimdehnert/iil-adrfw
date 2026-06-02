"""Bundled JSON Schema files for ADR validation."""

from pathlib import Path

SCHEMAS_DIR = Path(__file__).parent


def get_schema_dir() -> Path:
    """Return the path to the bundled schema directory."""
    return SCHEMAS_DIR
