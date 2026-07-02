"""Shared pytest fixtures for the examples/ E2E test suite.

Every ``test_e2e_*.py`` module exercises the FastMCP server (or the CLI)
against a small, private set of ADR fixtures staged into its own
``_test_adrs_*`` directory. That staging used to run as an *import-time*
side effect — module-level ``shutil.rmtree`` / ``.mkdir`` / ``shutil.copy``
plus ``os.environ[...] = ...`` executed the moment pytest collected the
file. Because ``IIL_ADRFW_ADRS_DIR`` / ``IIL_ADRFW_SCHEMAS_DIR`` /
``IIL_ADRFW_REPO_ROOT`` are process-wide keys, whichever module was
imported *last* under pytest-randomly's shuffled collection order "won"
the env vars, making the whole suite collection-order dependent. Every
module then carried a word-for-word ``_isolate_env`` autouse fixture to
patch around exactly that.

This conftest centralizes both concerns into a single implementation:

- ``_prepare_test_dirs`` (module-scoped, autouse) recreates a module's
  fixture directories and calls its ``_stage_fixtures()`` hook once, during
  fixture setup — never at import time.
- ``_isolate_env`` (function-scoped, autouse) re-points the
  ``IIL_ADRFW_*`` env vars at this module's directories before *every*
  test, via ``monkeypatch.setenv`` (never raw ``os.environ`` mutation).
  The server resolves these vars fresh per call (no caching), so per-test
  ``setenv`` is what actually gives each module isolation.

A test module opts in by declaring module-level ``pathlib.Path`` constants:

- ``ADRS_DIR`` (required if the module needs staged ADRs)
- ``SCHEMAS_DIR`` / ``REPO_ROOT`` / ``WORKSPACE`` (optional; mapped to the
  matching env var if present)
- ``TEST_DIRS`` (optional tuple of extra scratch dirs beyond ``ADRS_DIR``,
  e.g. ``test_e2e_diff.py``'s left/right comparison directories)
- ``_stage_fixtures()`` (optional callable that copies/writes the actual
  fixture files into the now-empty directories)
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_ENV_VAR_BY_ATTR = {
    "ADRS_DIR": "IIL_ADRFW_ADRS_DIR",
    "SCHEMAS_DIR": "IIL_ADRFW_SCHEMAS_DIR",
    "REPO_ROOT": "IIL_ADRFW_REPO_ROOT",
    "WORKSPACE": "IIL_ADRFW_REPO_ROOT",
}


@pytest.fixture(autouse=True, scope="module")
def _prepare_test_dirs(request: pytest.FixtureRequest) -> None:
    """Recreate this module's fixture directories once, in fixture setup.

    Mirrors the previous import-time behavior (wipe + recreate + stage)
    exactly, just moved out of module-import side effects and into fixture
    setup so nothing in examples/*.py runs I/O at collection time.
    """
    module = request.module
    dirs: tuple[Path, ...] = tuple(getattr(module, "TEST_DIRS", ()))
    if not dirs:
        adrs_dir = getattr(module, "ADRS_DIR", None)
        dirs = (adrs_dir,) if adrs_dir is not None else ()

    for directory in dirs:
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    stage = getattr(module, "_stage_fixtures", None)
    if callable(stage):
        stage()


@pytest.fixture(autouse=True)
def _isolate_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-point IIL_ADRFW_* env vars at this module's dirs before each test.

    One shared implementation replacing 9 word-for-word duplicated
    ``_isolate_env`` fixtures.
    """
    module = request.module
    for attr, var in _ENV_VAR_BY_ATTR.items():
        value = getattr(module, attr, None)
        if value is not None:
            monkeypatch.setenv(var, str(value))
