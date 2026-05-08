"""Cross-repo validation.

The killer use case from ADR-188 v1.1: before transitioning a draft ADR to
'accepted', verify that what the ADR claims is consistent with what the
consumer-repos already do. If 8 repos use UUID and the ADR says BIGINT,
the ADR is wrong, not the repos.

This module implements Class-1 detection (direct schema conflicts) for the
canonical case: tenant_id field type. Class-2 (LLM samples) and Class-3
(aggregation patterns) are stubbed — they need a real LLM call and a richer
codebase model respectively, which is out of scope for the skeleton.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import libcst as cst
from libcst.metadata import PositionProvider

from iil_adrfw.domain import ADR
from iil_adrfw.domain.cross_repo import (
    ConflictClass,
    ConflictConfidence,
    CrossRepoConflict,
    CrossRepoReport,
    RepoSample,
)


@dataclass
class ConsumerRepoLayout:
    """Where to find a consumer-repo on disk."""

    name: str                # 'meiki-hub', 'bfagent', ...
    root: Path               # local checkout root
    model_globs: tuple[str, ...] = ("**/models.py", "**/models/*.py", "**/models/**/*.py")
    sql_globs: tuple[str, ...] = ("**/db/*.sql", "**/migrations/*.sql")


# --- Class 1: tenant_id field type aggregation ---


class _TenantIdTypeExtractor(cst.CSTVisitor):
    """Walk a Python module, return list of (line, field_type_name) for every
    `tenant_id = models.<X>Field(...)` assignment in a Model subclass.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        super().__init__()
        self.findings: list[tuple[int, str, str]] = []  # (line, field_type, class_name)
        self._class_stack: list[str] = []
        self._class_is_model: list[bool] = []

    def _is_model_class(self, node: cst.ClassDef) -> bool:
        for base in node.bases:
            value = base.value
            if isinstance(value, cst.Name) and value.value == "Model":
                return True
            if (
                isinstance(value, cst.Attribute)
                and isinstance(value.value, cst.Name)
                and value.value.value == "models"
                and value.attr.value == "Model"
            ):
                return True
        return False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:
        self._class_stack.append(node.name.value)
        self._class_is_model.append(self._is_model_class(node))
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self._class_stack.pop()
        self._class_is_model.pop()

    def visit_Assign(self, node: cst.Assign) -> bool | None:
        if not self._class_is_model or not self._class_is_model[-1]:
            return False
        if len(node.targets) != 1:
            return False
        target = node.targets[0].target
        if not (isinstance(target, cst.Name) and target.value == "tenant_id"):
            return False

        field_name = self._extract_field_name(node.value)
        if field_name is None:
            return False
        try:
            pos = self.get_metadata(PositionProvider, node)
            line = pos.start.line
        except KeyError:
            line = 0
        self.findings.append((line, field_name, self._class_stack[-1]))
        return False

    @staticmethod
    def _extract_field_name(value: cst.BaseExpression) -> str | None:
        if isinstance(value, cst.Call):
            func = value.func
            if isinstance(func, cst.Attribute) and isinstance(func.value, cst.Name):
                if func.value.value == "models":
                    return func.attr.value
            if isinstance(func, cst.Name) and func.value.endswith("Field"):
                return func.value
        return None


def _sql_tenant_id_type(text: str) -> list[tuple[int, str]]:
    """Find tenant_id column declarations in a SQL file.
    Returns list of (line, type_name)."""
    findings: list[tuple[int, str]] = []
    pattern = re.compile(r"\btenant_id\s+(\w+)", re.IGNORECASE)
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip obvious comment lines
        stripped = line.strip()
        if stripped.startswith("--") or stripped.startswith("/*"):
            continue
        m = pattern.search(line)
        if m:
            findings.append((lineno, m.group(1).upper()))
    return findings


def _scan_python_models(repo: ConsumerRepoLayout) -> list[RepoSample]:
    """Scan all Python model files in the repo for tenant_id field types."""
    samples: list[RepoSample] = []
    for glob in repo.model_globs:
        for py_file in repo.root.glob(glob):
            try:
                source = py_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            try:
                module = cst.parse_module(source)
            except cst.ParserSyntaxError:
                continue
            wrapper = cst.MetadataWrapper(module)
            extractor = _TenantIdTypeExtractor()
            wrapper.visit(extractor)
            for line, field_type, class_name in extractor.findings:
                snippet = source.splitlines()[line - 1] if line > 0 else ""
                samples.append(RepoSample(
                    repo=repo.name,
                    file=str(py_file.relative_to(repo.root)),
                    line_start=line,
                    line_end=line,
                    snippet=snippet.strip(),
                    extracted_value=field_type,
                ))
    return samples


def _scan_sql_schemas(repo: ConsumerRepoLayout) -> list[RepoSample]:
    """Scan all SQL files in the repo for tenant_id column declarations."""
    samples: list[RepoSample] = []
    for glob in repo.sql_globs:
        for sql_file in repo.root.glob(glob):
            try:
                text = sql_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            for line, type_name in _sql_tenant_id_type(text):
                snippet = text.splitlines()[line - 1] if line > 0 else ""
                samples.append(RepoSample(
                    repo=repo.name,
                    file=str(sql_file.relative_to(repo.root)),
                    line_start=line,
                    line_end=line,
                    snippet=snippet.strip(),
                    extracted_value=type_name,
                ))
    return samples


# --- Type normalization ---
# Maps Django field types and SQL types to a canonical 'family' so we can
# compare across the language boundary.

_TYPE_FAMILIES = {
    # UUID family
    "UUIDField": "uuid",
    "UUID": "uuid",
    # Big-integer family
    "BigIntegerField": "bigint",
    "BIGINT": "bigint",
    "BIGSERIAL": "bigint",  # actually a sequence type but tenant_id semantics match
    # Plain integer family
    "IntegerField": "int",
    "PositiveIntegerField": "int",
    "INT": "int",
    "INTEGER": "int",
    "SERIAL": "int",
}


def _to_family(value: str | None) -> str:
    if not value:
        return "unknown"
    return _TYPE_FAMILIES.get(value, "other")


# --- Core validation ---


def validate_cross_repo(
    adr: ADR,
    consumer_repos: list[ConsumerRepoLayout],
) -> CrossRepoReport:
    """Run cross-repo validation for a single ADR.

    Currently focuses on Class 1 conflicts for the tenant_id type aspect.
    Architecture is set up for adding more aspect-specific detectors.

    The ADR's origin-repo (adr.repo) is automatically excluded from the
    consumer-repo set: the origin contains the implementation OF the ADR's
    claim, not an independent consumer. Including it would dilute the
    consensus signal.
    """
    start = time.monotonic()
    scanned: list[str] = []
    unreachable: list[str] = []
    excluded_origin: list[str] = []
    conflicts: list[CrossRepoConflict] = []

    # Aggregate tenant_id evidence across all repos
    py_samples: list[RepoSample] = []
    sql_samples: list[RepoSample] = []
    for repo in consumer_repos:
        if adr.repo and repo.name == adr.repo:
            excluded_origin.append(repo.name)
            continue
        if not repo.root.exists():
            unreachable.append(repo.name)
            continue
        scanned.append(repo.name)
        py_samples.extend(_scan_python_models(repo))
        sql_samples.extend(_scan_sql_schemas(repo))

    all_samples = py_samples + sql_samples

    # Determine consumer-repo consensus
    family_counter: Counter[str] = Counter(_to_family(s.extracted_value) for s in all_samples)
    family_counter.pop("unknown", None)

    if not family_counter:
        # Nothing found — not necessarily a problem, just nothing to compare
        runtime_ms = int((time.monotonic() - start) * 1000)
        return CrossRepoReport(
            adr_id=adr.id,
            validated_at=datetime.now(timezone.utc),
            consumer_repos_scanned=tuple(scanned),
            repos_unreachable=tuple(unreachable),
            conflicts=[],
            runtime_ms=runtime_ms,
        )

    # The consumer-repo consensus is the most common family
    consensus_family, consensus_count = family_counter.most_common(1)[0]
    consensus_share = consensus_count / sum(family_counter.values())

    # Now: what does the ADR claim about tenant_id?
    # We extract this from rules whose checker mentions tenant_id type.
    adr_claim_family = _detect_adr_tenant_id_claim(adr)

    if adr_claim_family is None:
        # ADR makes no explicit claim — Class 3 territory, skip for now
        runtime_ms = int((time.monotonic() - start) * 1000)
        return CrossRepoReport(
            adr_id=adr.id,
            validated_at=datetime.now(timezone.utc),
            consumer_repos_scanned=tuple(scanned),
            repos_unreachable=tuple(unreachable),
            conflicts=[],
            runtime_ms=runtime_ms,
        )

    # Conflict detection: ADR claim vs consumer-repo consensus
    if adr_claim_family != consensus_family:
        # Find samples whose family differs from the ADR claim — these are
        # the most damning evidence
        conflicting_samples = tuple(
            s for s in all_samples
            if _to_family(s.extracted_value) != adr_claim_family
        )
        affected_repos = tuple(sorted({s.repo for s in conflicting_samples}))

        # Confidence: PROVEN if 100% of consumer-repos disagree with ADR,
        # HIGH if >75%, MEDIUM otherwise
        if consensus_share >= 0.99:
            confidence = ConflictConfidence.PROVEN
        elif consensus_share >= 0.75:
            confidence = ConflictConfidence.HIGH
        else:
            confidence = ConflictConfidence.MEDIUM

        suggestion = _build_suggestion(adr_claim_family, consensus_family, consensus_share)

        conflicts.append(CrossRepoConflict(
            adr_id=adr.id,
            rule_id=None,  # ADR-level
            conflict_class=ConflictClass.DIRECT_SCHEMA,
            confidence=confidence,
            claim=f"tenant_id field family = '{adr_claim_family}'",
            reality=(
                f"{consensus_count}/{sum(family_counter.values())} samples in consumer-repos "
                f"use family '{consensus_family}' ({consensus_share:.0%}); "
                f"{', '.join(f'{f}: {n}' for f, n in family_counter.items())}"
            ),
            evidence=conflicting_samples[:10],  # cap evidence for readability
            affected_repos=affected_repos,
            suggestion=suggestion,
            blocks_publish=(confidence in (ConflictConfidence.PROVEN, ConflictConfidence.HIGH)),
        ))

    runtime_ms = int((time.monotonic() - start) * 1000)
    return CrossRepoReport(
        adr_id=adr.id,
        validated_at=datetime.now(timezone.utc),
        consumer_repos_scanned=tuple(scanned),
        repos_unreachable=tuple(unreachable),
        conflicts=conflicts,
        runtime_ms=runtime_ms,
    )


def _detect_adr_tenant_id_claim(adr: ADR) -> str | None:
    """Inspect the ADR's rules to determine what it claims about tenant_id type."""
    for rule in adr.rules:
        spec = rule.checker_spec
        # Regex-based rule looking at SQL with 'tenant_id'
        if spec.get("type") == "regex":
            pat = spec.get("pattern", "")
            if "tenant_id" in pat:
                # The pattern uses negative lookahead like `(?!UUID)(BIGINT|...)` —
                # whichever type is in the NEGATIVE lookahead is the ALLOWED type
                m = re.search(r"\(\?!\s*([A-Za-z_]+)\s*\)", pat)
                if m:
                    return _to_family(m.group(1))
        # AST-based rule for Django models
        if spec.get("type") == "ast" and rule.rule_id == "tenant-id-bigint":
            return "bigint"
    # Fallback: look at rationale_summary text for explicit hints
    summary = (adr.rationale_summary or "").lower()
    if "tenant_id uuid" in summary or "uuid tenant_id" in summary:
        return "uuid"
    if "tenant_id bigint" in summary or "bigint tenant_id" in summary:
        return "bigint"
    return None


def _build_suggestion(claimed: str, observed: str, share: float) -> str:
    return (
        f"The ADR claims tenant_id is '{claimed}' but consumer-repos overwhelmingly "
        f"({share:.0%}) use '{observed}'. Two paths:\n"
        f"  1. AMEND the ADR to match consumer-repo reality (use '{observed}'). "
        f"     Lowest cost — recommended unless the claim has a specific reason.\n"
        f"  2. MIGRATE consumer-repos to match the ADR (use '{claimed}'). "
        f"     High cost — only justified by hard regulatory or performance need.\n"
        f"Decision should be documented in an Amendment with rationale."
    )
