"""libcst-based Python AST checkers.

The general PythonASTChecker class consumes a structured spec. For the skeleton
we ship one well-tested checker — tenant_id_bigint — and the structure to add more.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import libcst as cst
from libcst.metadata import PositionProvider

from iil_adrfw.domain import (
    DifferentialDiagnostic,
    FixSuggestion,
    Rule,
    RuleViolation,
)


class _TenantIdFieldVisitor(cst.CSTVisitor):
    """Walk a module, find every `tenant_id = models.<X>Field(...)` assignment
    inside a class that inherits from Model. Record the field type used.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, allowed_field: str = "BigIntegerField") -> None:
        super().__init__()
        self.allowed_field = allowed_field
        self.findings: list[dict[str, Any]] = []
        self._class_stack: list[cst.ClassDef] = []

    def _inherits_from_model(self, node: cst.ClassDef) -> bool:
        for base in node.bases:
            value = base.value
            # `Model`
            if isinstance(value, cst.Name) and value.value == "Model":
                return True
            # `models.Model`
            if (
                isinstance(value, cst.Attribute)
                and isinstance(value.value, cst.Name)
                and value.value.value == "models"
                and value.attr.value == "Model"
            ):
                return True
        return False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:
        self._class_stack.append(node)
        return True

    def leave_ClassDef_body(self, node: cst.ClassDef) -> None:
        self._class_stack.pop()

    def visit_Assign(self, node: cst.Assign) -> bool | None:
        if not self._class_stack:
            return False
        cls = self._class_stack[-1]
        if not self._inherits_from_model(cls):
            return False

        # We want exactly: tenant_id = models.XField(...) OR tenant_id = XField(...)
        if len(node.targets) != 1:
            return False
        target = node.targets[0].target
        if not (isinstance(target, cst.Name) and target.value == "tenant_id"):
            return False

        value = node.value
        field_name = self._extract_field_name(value)
        if field_name is None:
            return False

        if field_name == self.allowed_field:
            return False  # compliant — no finding

        # Violation found
        try:
            pos = self.get_metadata(PositionProvider, node)
            line_start = pos.start.line
            line_end = pos.end.line
        except KeyError:
            line_start = line_end = 0

        self.findings.append({
            "field_name": field_name,
            "class_name": cls.name.value,
            "line_start": line_start,
            "line_end": line_end,
        })
        return False

    @staticmethod
    def _extract_field_name(value: cst.BaseExpression) -> str | None:
        """Extract the Field class name from `models.XField(...)` or `XField(...)`."""
        if isinstance(value, cst.Call):
            func = value.func
            if isinstance(func, cst.Attribute) and isinstance(func.value, cst.Name):
                if func.value.value == "models":
                    return func.attr.value
            if isinstance(func, cst.Name):
                if func.value.endswith("Field"):
                    return func.value
        return None


def check_tenant_id_bigint(
    rule: Rule, file_path: Path, source: str
) -> list[RuleViolation]:
    """Check that tenant_id is BigIntegerField in Django models."""
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return []  # syntax errors are someone else's problem

    wrapper = cst.MetadataWrapper(module)
    visitor = _TenantIdFieldVisitor(allowed_field="BigIntegerField")
    wrapper.visit(visitor)

    violations: list[RuleViolation] = []
    for finding in visitor.findings:
        actual = f"models.{finding['field_name']}"
        expected = "models.BigIntegerField"
        # crude semantic distance: exact match=0, IntegerField=0.3, totally different=0.9
        if "Integer" in finding["field_name"]:
            distance = 0.3
            cause = "outdated_template"
        else:
            distance = 0.9
            cause = "unaware_of_rule"

        diag = DifferentialDiagnostic(
            expected_pattern=expected,
            actual_pattern=actual,
            semantic_distance=distance,
            likely_cause=cause,
            blast_radius=rule.blast_radius,
        )

        # Build fix suggestions from the rule's spec
        suggestions: list[FixSuggestion] = []
        for s in rule.fix_suggestions:
            suggestions.append(
                FixSuggestion(
                    description=s.get("description", ""),
                    confidence=float(s.get("confidence", 0.0)),
                    automated=bool(s.get("automated", False)),
                    code_transform=s.get("code_transform"),
                    side_effects=tuple(s.get("side_effects", [])),
                )
            )

        violations.append(
            RuleViolation(
                rule_id=rule.global_id,
                severity=rule.severity,
                file=str(file_path),
                line_start=finding["line_start"],
                line_end=finding["line_end"],
                expected=expected,
                actual=actual,
                diagnostic=diag,
                suggestions=tuple(suggestions),
            )
        )
    return violations


# Generic AST checker that dispatches via the rule's `match` pattern.
# For the skeleton: if the pattern signature looks like the tenant_id
# BigIntegerField rule, use the specialized checker. This is a deliberate
# simplification — Stage 2 will add a real pattern-language interpreter.
class PythonASTChecker:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec

    def check(self, rule: Rule, file_path: Path, source: str) -> list[RuleViolation]:
        # Pattern-routing: in real impl, parse spec.pattern.match.
        # For the skeleton, we use the rule_id as the dispatch key.
        if rule.rule_id == "tenant-id-bigint":
            return check_tenant_id_bigint(rule, file_path, source)
        return []
