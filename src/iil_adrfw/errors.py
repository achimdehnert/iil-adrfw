"""Shared exception types.

Kept dependency-free and importable from anywhere in the package (including
``checkers``), so no module has to reach back into ``iil_adrfw/__init__.py``.
"""

from __future__ import annotations


class MissingExtraError(ImportError):
    """An optional extra is required for the requested operation but not installed.

    Carries the install command in its message. The CLI maps this to exit code 2
    (configuration error) rather than 3 (internal error) — a missing extra is
    something the operator fixes in their install, not a bug in the framework.
    """

    def __init__(self, extra: str, what: str) -> None:
        self.extra = extra
        super().__init__(
            f"{what} needs the optional '{extra}' extra. Install it with: pip install 'iil-adrfw[{extra}]'"
        )
