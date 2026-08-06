"""Checker protocol and registry. Concrete checkers live in sibling modules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from iil_adrfw.domain import Rule, RuleViolation
from iil_adrfw.errors import MissingExtraError


class Checker(Protocol):
    """A checker takes a rule and a file path, returns violations."""

    def check(self, rule: Rule, file_path: Path, source: str) -> list[RuleViolation]: ...


_REGISTRY: dict[str, Checker] = {}


def register(name: str, checker: Checker) -> None:
    _REGISTRY[name] = checker


def get(name: str) -> Checker | None:
    return _REGISTRY.get(name)


def build_checker(rule: Rule) -> Checker | None:
    """Build a concrete checker from a rule's checker_spec."""
    spec = rule.checker_spec
    spec_type = spec.get("type")

    if spec_type == "custom":
        # entry_point: 'pkg.module:function'
        ep = spec["entry_point"]
        return _REGISTRY.get(ep)

    if spec_type == "ast" and spec.get("language") == "python":
        # This is the real libcst boundary: the AST checkers ship as the optional
        # `[checkers]` extra, so a lean CI install reaches here only when a rule
        # actually asks for AST checking. Fail with the fix, not a bare traceback.
        try:
            from iil_adrfw.checkers.python_ast import PythonASTChecker
        except ImportError as exc:
            raise MissingExtraError("checkers", f"Rule {rule.global_id!r}") from exc

        return PythonASTChecker(spec)

    return None
