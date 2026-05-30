"""Constitution graph and query implementation.

The graph is built lazily from the loaded ADR set. It indexes:
- domain -> [adr_id]                    (domain_index)
- concept-token -> [adr_id]             (concept_index, built from rationale+rules+glossary)
- repo -> [adr_id]                      (repo_index)
- adr_id -> ADR                         (id_index)

adr_query returns:
- primary citations (ADRs that directly address the query)
- supporting citations (ADRs adjacent in the graph)
- open_questions if the query touches an unanswered area
- confidence based on match strength
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from iil_adrfw.domain import ADR, OpenQuestion, Status

# --- Tokenization for concept index ---

# Match german + english word characters of length >= 3
_TOKEN_RE = re.compile(r"[a-zA-Z\u00c0-\u017f][a-zA-Z\u00c0-\u017f0-9_-]{2,}")
# Common stopwords (DE + EN). Kept compact — full lists hurt recall without helping precision much.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "for", "with", "from", "into", "of", "in", "on", "to", "by", "at",
    "as", "this", "that", "these", "those", "be", "been", "being",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "und", "oder", "aber", "ist", "sind", "war", "waren", "fuer", "für",
    "mit", "von", "in", "zu", "bei", "an", "auf", "im", "wird", "werden",
    "siehe", "z.b", "etc",
})


def _tokenize(text: str) -> set[str]:
    return {
        m.group(0).lower()
        for m in _TOKEN_RE.finditer(text or "")
        if m.group(0).lower() not in _STOPWORDS
    }


# --- Graph ---


@dataclass
class ConstitutionGraph:
    """Indexed view over the ADR set. Cheap to build, deterministic, no LLM calls."""

    adrs: list[ADR]
    by_id: dict[str, ADR] = field(default_factory=dict)
    by_domain: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_repo: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_concept: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_consumer: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def build(cls, adrs: Iterable[ADR]) -> ConstitutionGraph:
        g = cls(adrs=list(adrs))
        for a in g.adrs:
            g.by_id[a.id] = a
            for d in a.domains:
                g.by_domain[d].append(a.id)
            if a.repo:
                g.by_repo[a.repo].append(a.id)
            for c in a.consumers:
                g.by_consumer[c].append(a.id)
            # Concept tokens come from a deliberately limited surface to keep precision high
            tokens: set[str] = set()
            tokens.update(_tokenize(a.title))
            tokens.update(_tokenize(a.rationale_summary))
            for r in a.rules:
                tokens.update(_tokenize(r.title))
            for q in a.open_questions:
                tokens.update(_tokenize(q.question))
            for raw_glossary in a.raw_frontmatter.get("glossary", []) or []:
                tokens.update(_tokenize(raw_glossary.get("term", "")))
                tokens.update(_tokenize(raw_glossary.get("definition", "")))
            for token in tokens:
                g.by_concept[token].append(a.id)
        return g

    def adrs_for_domain(self, domain: str) -> list[ADR]:
        ids = self.by_domain.get(domain, [])
        return [self.by_id[i] for i in ids if i in self.by_id]

    def adrs_matching_concepts(self, concepts: set[str]) -> list[tuple[ADR, int]]:
        """Return (adr, hit_count) ranked descending. Includes proposed ADRs
        because consumers need to know about decisions in flight. Status is
        carried in the citation."""
        scores: defaultdict[str, int] = defaultdict(int)
        for c in concepts:
            for adr_id in self.by_concept.get(c, []):
                scores[adr_id] += 1
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        return [
            (self.by_id[i], n)
            for i, n in ranked
            if i in self.by_id and self.by_id[i].status not in (Status.REJECTED, Status.SUPERSEDED, Status.DEPRECATED)
        ]

    def adrs_for_path(self, path: str) -> list[ADR]:
        """ADRs whose scope.include_paths or drift_check_paths match this path.
        Includes proposed ADRs (consumers need to know about in-flight decisions)."""
        from fnmatch import fnmatch

        results: list[ADR] = []
        for adr in self.adrs:
            if adr.status in (Status.REJECTED, Status.SUPERSEDED, Status.DEPRECATED):
                continue
            scope_globs = adr.raw_frontmatter.get("scope", {}).get("include_paths") or []
            drift_globs = list(adr.drift_check_paths)
            if any(fnmatch(path, g) for g in scope_globs + drift_globs):
                results.append(adr)
        return results

    def all_open_questions(self) -> list[tuple[ADR, OpenQuestion]]:
        out = []
        for adr in self.adrs:
            for q in adr.open_questions:
                if q.status == "open":
                    out.append((adr, q))
        return out


# --- Query result types ---


@dataclass(frozen=True)
class QueryCitation:
    adr_id: str
    title: str
    status: str
    relevance: str  # 'primary' | 'supporting' | 'related-via-domain' | 'open-question'
    excerpt: str
    matched_concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryResult:
    primary_answer: str
    citations: tuple[QueryCitation, ...]
    open_questions: tuple[tuple[str, str, str], ...]  # (adr_id, q_id, question)
    confidence: float  # 0.0 .. 1.0
    routing: str  # which strategy resolved the query: 'domain' | 'concept' | 'path' | 'mixed'


# --- Query function ---


def execute_query(
    graph: ConstitutionGraph,
    question: str | None = None,
    domain: str | None = None,
    path: str | None = None,
) -> QueryResult:
    """Answer a constitutional query.

    Exactly one of question/domain/path should drive the result; combinations
    AND-narrow.
    """
    primary: list[ADR] = []
    matched_concepts: dict[str, set[str]] = {}
    routing = "concept"

    # Domain-driven path
    if domain:
        primary = graph.adrs_for_domain(domain)
        routing = "domain"

    # Path-driven
    if path:
        path_matches = graph.adrs_for_path(path)
        if primary:
            primary = [a for a in primary if a in path_matches]
            routing = "mixed"
        else:
            primary = path_matches
            routing = "path"

    # Concept-driven (text question)
    if question:
        question_concepts = _tokenize(question)
        concept_hits = graph.adrs_matching_concepts(question_concepts)
        if primary:
            # Re-rank existing primary by concept score
            concept_scores = {a.id: n for a, n in concept_hits}
            primary = sorted(primary, key=lambda a: -concept_scores.get(a.id, 0))
            for a, n in concept_hits:
                matched_concepts[a.id] = question_concepts & set(graph.by_concept.keys())
            routing = "mixed"
        else:
            primary = [a for a, _ in concept_hits[:5]]
            for a, n in concept_hits[:5]:
                matched_concepts[a.id] = question_concepts & {
                    c for c in question_concepts if a.id in graph.by_concept.get(c, [])
                }
            routing = "concept"

    primary = [a for a in primary if a.status not in (Status.REJECTED, Status.SUPERSEDED, Status.DEPRECATED)]

    # Find open questions related to the query
    related_open: list[tuple[str, str, str]] = []
    if question:
        question_concepts = _tokenize(question)
        for adr, q in graph.all_open_questions():
            q_concepts = _tokenize(q.question)
            if question_concepts & q_concepts:
                related_open.append((adr.id, q.id, q.question))

    # Confidence: 0 if no hits, scales with primary count and concept overlap
    if not primary:
        confidence = 0.0
        primary_answer = (
            f"Die Verfassung enthält keine Entscheidung zu '{question or domain or path}'. "
            "Das ist eine Lücke — erwäge ein neues ADR oder reagiere mit `adr_propose`."
        )
    elif len(primary) == 1:
        confidence = 0.85 if matched_concepts.get(primary[0].id) else 0.65
        primary_answer = primary[0].rationale_summary or primary[0].title
    else:
        confidence = 0.6 if related_open else 0.7
        primary_answer = (
            f"{len(primary)} ADRs treffen zu. Hauptaussage: {primary[0].rationale_summary or primary[0].title}"
        )

    citations = tuple(
        QueryCitation(
            adr_id=a.id,
            title=a.title,
            status=a.status.value,
            relevance="primary" if i == 0 else "supporting",
            excerpt=(a.rationale_summary or a.title)[:240],
            matched_concepts=tuple(sorted(matched_concepts.get(a.id, set()))),
        )
        for i, a in enumerate(primary[:8])
    )

    return QueryResult(
        primary_answer=primary_answer,
        citations=citations,
        open_questions=tuple(related_open),
        confidence=confidence,
        routing=routing,
    )
