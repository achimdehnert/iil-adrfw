"""Checker protocol and registry. Concrete checkers live in sibling modules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from iil_adrfw.domain import Rule, RuleViolation


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
        from iil_adrfw.checkers.python_ast import PythonASTChecker

        return PythonASTChecker(spec)

    return None
