"""Cross-repo validation domain types.

Three classes of conflicts (see ADR-188 v1.1 lessons):
- Class 1: direct schema conflict — AST-detectable, high precision
- Class 2: semantic/intent conflict — needs LLM samples, lower precision
- Class 3: implicit-convention conflict — needs aggregation across all repos
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConflictClass(str, Enum):
    DIRECT_SCHEMA = "direct_schema"          # Class 1
    SEMANTIC_INTENT = "semantic_intent"       # Class 2
    IMPLICIT_CONVENTION = "implicit_convention"  # Class 3


class ConflictConfidence(str, Enum):
    """How confident the validator is in the finding.

    Class 1 findings are typically HIGH or PROVEN.
    Class 2 findings are MEDIUM at best — need human review.
    Class 3 findings are LOW unless aggregation pattern is statistically clear.
    """
    PROVEN = "proven"      # AST match, no ambiguity
    HIGH = "high"          # AST match with minor edge cases
    MEDIUM = "medium"      # heuristic match, plausible alternatives exist
    LOW = "low"            # weak signal, mostly informational


@dataclass(frozen=True)
class RepoSample:
    """A code excerpt from one repo, used as evidence in a cross-repo finding."""

    repo: str
    file: str
    line_start: int
    line_end: int
    snippet: str                      # the actual code text
    extracted_value: str | None       # parsed value: 'UUIDField', 'IntegerField', etc.


@dataclass(frozen=True)
class CrossRepoConflict:
    """A conflict between an ADR claim and the actual state of consumer repos."""

    adr_id: str
    rule_id: str | None               # if a specific rule, else ADR-level claim
    conflict_class: ConflictClass
    confidence: ConflictConfidence
    claim: str                        # what the ADR says
    reality: str                      # what consumer-repos actually do
    evidence: tuple[RepoSample, ...]  # samples backing the finding
    affected_repos: tuple[str, ...]
    suggestion: str                   # how to resolve: amend ADR, migrate code, or both
    blocks_publish: bool              # if True, ADR should not transition to 'accepted'


@dataclass
class CrossRepoReport:
    """Full report from a cross-repo validation run."""

    adr_id: str
    validated_at: datetime
    consumer_repos_scanned: tuple[str, ...]
    repos_unreachable: tuple[str, ...] = ()
    conflicts: list[CrossRepoConflict] = field(default_factory=list)
    runtime_ms: int = 0

    @property
    def has_blocking_conflicts(self) -> bool:
        return any(c.blocks_publish for c in self.conflicts)

    @property
    def class1_count(self) -> int:
        return sum(1 for c in self.conflicts if c.conflict_class == ConflictClass.DIRECT_SCHEMA)

    @property
    def class2_count(self) -> int:
        return sum(1 for c in self.conflicts if c.conflict_class == ConflictClass.SEMANTIC_INTENT)

    @property
    def class3_count(self) -> int:
        return sum(1 for c in self.conflicts if c.conflict_class == ConflictClass.IMPLICIT_CONVENTION)
