"""Load ADRs from markdown files with YAML frontmatter, plus sibling .rules.yaml files."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, time, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from iil_adrfw.domain import (
    ADR,
    Amendment,
    DecisionDriver,
    DeprecationStep,
    OpenQuestion,
    PerRepoStatus,
    Rule,
    Scope,
    Severity,
    SPOFMitigation,
    Status,
    TemporalRange,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(?:ADR-\d{3,5}\s*[—:-]\s*)?(.+?)\s*$", re.MULTILINE)

# Schema v3/v4 field rename aliases. Source -> target.
# 'target wins if both present' is the merge strategy throughout.
_FIELD_ALIASES: tuple[tuple[str, str], ...] = (
    ("decision-makers", "deciders"),
    ("superseded-by", "superseded_by"),
    ("depends-on", "depends_on"),
    ("conflicts-with", "conflicts_with"),
    ("relates_to", "related"),
    ("relates-to", "related"),
    ("related_adrs", "related"),
    ("last_verified", "last_reviewed"),
    ("adr_id", "id"),
    ("review", "review_status"),
    ("author", "owner"),
    ("date", "decision_date"),
    # Schema v4 new fields — hyphen forms
    ("reviewed-by", "reviewed_by"),
    ("ai-sparring-by", "ai_sparring_by"),
    ("doc-type", "doc_type"),
    ("status-history", "status_history"),
    ("decision-maker", "deciders"),
)


def original_frontmatter(md_path: Path) -> dict:
    """Parse a file's YAML frontmatter WITHOUT Phase-1 normalization.

    Used to inspect the author's original keys (e.g. for deprecation warnings)
    before aliases are rewritten to their canonical form. Returns {} if the
    file has no frontmatter block. Distinct from the domain object's
    `.raw_frontmatter`, which is the POST-normalization dict.
    """
    m = _FRONTMATTER_RE.match(md_path.read_text(encoding="utf-8"))
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def detect_legacy_aliases(frontmatter: dict) -> list[tuple[str, str]]:
    """Return [(legacy_key, canonical_key)] for every non-canonical alias present.

    Reuses the single-source `_FIELD_ALIASES` table — so it stays in lock-step
    with the loader's normalization. Pass the RAW frontmatter (see
    `original_frontmatter`); after `_normalize_frontmatter` the legacy keys are gone.
    """
    return [(legacy, canonical) for legacy, canonical in _FIELD_ALIASES if legacy in frontmatter]


# Fields stripped entirely — too low-frequency and/or semantically distinct
# from any schema field. They survive in the markdown body if needed.
# NOTE: "reviewed-by" was stripped in v3 but is now aliased to reviewed_by in v4.
_STRIPPED_FIELDS: frozenset[str] = frozenset(
    {
        "reviewed",
        "repos",
        # Tool-specific noise (Jekyll, audit transients, etc.):
        "nav_order",
        "parent",
        "commit",
        "product_name",
        "supersedes_check",
        "superseded_by_planned",
        # Revision metadata (not schema fields):
        "revised",
        "revision",
    }
)

# Filename pattern for id inference
_FILENAME_ID_RE = re.compile(r"^(ADR-\d{3,5})")

# Fields that should be arrays — auto-wrap scalars.
_AUTO_WRAP_FIELDS: tuple[str, ...] = (
    "deciders",
    "consulted",
    "informed",
    "domains",
    "amends",
)
# Values that mean "empty list" when seen as a scalar in an array field.
_EMPTY_LIST_SENTINELS: frozenset[str] = frozenset({"–", "-", "—", "n/a", "none", ""})


class ADRLoadError(Exception):
    pass


def _require_within(candidate: Path, base: Path, what: str) -> Path:
    """Resolve *candidate* and ensure it stays within *base* (both resolved).

    Guards against path-traversal and symlink-escape: an ADR file or its
    referenced ``rules_file`` must never cause a read outside the ADR directory
    tree. Both paths are ``resolve()``d (following symlinks) before comparison,
    so an absolute path, a ``../`` escape, or a symlink pointing elsewhere are
    all rejected. Raises ADRLoadError on any escape; returns the resolved path.
    """
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    if not candidate_resolved.is_relative_to(base_resolved):
        raise ADRLoadError(
            f"{candidate}: refuses to read outside the ADR directory "
            f"({what} resolves to {candidate_resolved}, outside {base_resolved})"
        )
    return candidate_resolved


def _normalize_status(raw: Any) -> Any:
    """Status normalization (Schema v3 C.2).
    Handles case ('Accepted'), quotes ('"accepted"'), version suffixes ('accepted (v2)').
    Returns lowercase canonical form. Unknown values pass through unchanged
    so the schema enum check produces a clear error message."""
    if not isinstance(raw, str):
        return raw
    s = raw.strip().strip('"').strip("'").lower()
    s = re.sub(r"\s*\(v[\d.]+\)\s*$", "", s)
    s = re.sub(r"\s*\(revision[^)]*\)\s*$", "", s)
    return s


def _infer_title(frontmatter: dict, body: str, md_path: Path) -> str:
    """Title inference fallback chain (Schema v3 C.5)."""
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    # Try first H1 in body
    m = _H1_RE.search(body or "")
    if m:
        candidate = m.group(1).strip()
        if candidate:
            return candidate
    # Filename slug fallback: ADR-NNN-multi-tenant-cron.md -> 'multi tenant cron'
    stem = md_path.stem
    slug_match = re.match(r"^ADR-\d{3,5}-(.+)$", stem)
    if slug_match:
        return slug_match.group(1).replace("-", " ").replace("_", " ")
    return "(untitled ADR)"


def _normalize_frontmatter(
    frontmatter: dict,
    body: str,
    md_path: Path,
) -> dict:
    """Phase 1 of the loader — tolerant pre-process.

    Always runs (Schema v3 design decision: normalization is the default).
    The 'raw=True' flag in load_adr skips this function entirely.

    Steps applied (Schema v3 C.1 - C.8):
      C.1  Field renames (aliases)
      C.2  Status normalization
      C.3  Scalar-to-list wrapping
      C.4  Reference field normalization
      C.5  Title inference
      C.6  Amended-format normalization (legacy date → last_reviewed)
      C.7  `implemented` field handling
      C.8  Strip unknown/tool-specific properties
    """
    # C.1 — Field renames. Target-wins-if-both rule for safety.
    for legacy, canonical in _FIELD_ALIASES:
        if legacy in frontmatter:
            if canonical not in frontmatter:
                frontmatter[canonical] = frontmatter.pop(legacy)
            else:
                # Both forms present — drop the legacy form, keep canonical
                frontmatter.pop(legacy)

    # C.1b — Date fields: YAML auto-parses dates as datetime.date, schema expects strings
    for date_field in (
        "decision_date",
        "last_reviewed",
        "updated",
        "valid_from",
        "valid_to",
        "knowledge_from",
        "sunset_after",
    ):
        v = frontmatter.get(date_field)
        if v is not None and not isinstance(v, str):
            frontmatter[date_field] = str(v)[:10] if hasattr(v, "year") else str(v)
        elif isinstance(v, str):
            # Strip version suffixes like '2026-03-11-v1.2' from any date field
            m_date = re.match(r"^(\d{4}-\d{2}-\d{2})", v)
            if m_date and len(v) > 10:
                frontmatter[date_field] = m_date.group(1)

    # C.1b-v4 — Schema v4: normalize date fields nested in reviewed_by / ai_sparring_by
    for list_field in ("reviewed_by", "ai_sparring_by"):
        items = frontmatter.get(list_field)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "date" in item:
                    v = item["date"]
                    if v is not None and not isinstance(v, str):
                        item["date"] = str(v)[:10] if hasattr(v, "year") else str(v)

    # C.v4-migration — reviewed_by / ai_sparring_by: strip legacy string/string-array formats.
    # Schema v4 requires array of HumanReview/AISparring objects. Strings cannot be auto-migrated
    # (missing required date/verdict/role fields). Stripped → Bus Factor warning fires correctly.
    for list_field in ("reviewed_by", "ai_sparring_by"):
        rv = frontmatter.get(list_field)
        if rv is None:
            continue
        if not isinstance(rv, list):
            # Scalar string (legacy: "Principal Architect") — strip
            frontmatter.pop(list_field)
        elif rv and not isinstance(rv[0], dict):
            # Array of strings (legacy: ["Claude (Sparring, date)"]) — strip
            frontmatter.pop(list_field)

    # C.1c — Title: enforce maxLength 120 (truncate if needed)
    title = frontmatter.get("title")
    if isinstance(title, str) and len(title) > 120:
        frontmatter["title"] = title[:117] + "..."

    # C.1d — implementation_evidence: if string, wrap to list
    ie = frontmatter.get("implementation_evidence")
    if isinstance(ie, str):
        frontmatter["implementation_evidence"] = [ie] if ie.strip() else []

    # C.2 — Status normalization
    if "status" in frontmatter:
        frontmatter["status"] = _normalize_status(frontmatter["status"])

    # C.3 — Scalar-to-list auto-wrapping
    for field in _AUTO_WRAP_FIELDS:
        v = frontmatter.get(field)
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.lower() in _EMPTY_LIST_SENTINELS:
                frontmatter[field] = []
            else:
                frontmatter[field] = [v]

    # C.4 — Reference field normalization (string-form refs to arrays)
    _ref_fields = (
        "supersedes",
        "superseded_by",
        "depends_on",
        "consolidates",
        "conflicts_with",
        "informs",
        "related",
        "amends",
    )
    for field in _ref_fields:
        v = frontmatter.get(field)
        if isinstance(v, str):
            frontmatter[field] = list(_normalize_refs(v))
        elif isinstance(v, list):
            # Normalize list items: extract ADR-NNN from filenames etc.
            frontmatter[field] = list(_normalize_refs(v))

    # C.5a — ID inference from filename (if missing)
    if "id" not in frontmatter or not frontmatter.get("id"):
        m_id = _FILENAME_ID_RE.match(md_path.stem)
        if m_id:
            frontmatter["id"] = m_id.group(1)

    # C.5b — Title inference (only if missing)
    if "title" not in frontmatter or not frontmatter.get("title"):
        frontmatter["title"] = _infer_title(frontmatter, body, md_path)
    # Re-apply truncation after inference
    if isinstance(frontmatter.get("title"), str) and len(frontmatter["title"]) > 120:
        frontmatter["title"] = frontmatter["title"][:117] + "..."

    # C.5c — Domains default (if missing, infer from tags or set generic)
    if "domains" not in frontmatter or not frontmatter.get("domains"):
        # Try to derive from tags if available
        tags = frontmatter.get("tags", [])
        if isinstance(tags, list) and tags:
            frontmatter["domains"] = [tags[0].lower().replace(" ", "-")]
        else:
            frontmatter["domains"] = ["general"]

    # C.5d — Scope: if string (legacy), strip it (not schema-conformant)
    if isinstance(frontmatter.get("scope"), str):
        frontmatter.pop("scope")

    # C.5e — decision_date: if still missing, try to infer from valid_from or set epoch
    if "decision_date" not in frontmatter or not frontmatter.get("decision_date"):
        vf = frontmatter.get("valid_from")
        if vf:
            frontmatter["decision_date"] = str(vf)[:10]
        else:
            frontmatter["decision_date"] = "1970-01-01"

    # C.5f — deciders: default to owner or generic if missing
    if "deciders" not in frontmatter or not frontmatter.get("deciders"):
        owner = frontmatter.get("owner")
        if owner:
            frontmatter["deciders"] = [owner]
        else:
            frontmatter["deciders"] = ["(unknown)"]

    # C.5g — implementation_status normalization (non-standard values)
    _IMPL_STATUS_ALIAS = {
        "not_started": "none",
        "done": "implemented",
        "superseded": "none",
        "not started": "none",
    }
    impl_s = frontmatter.get("implementation_status")
    if isinstance(impl_s, str):
        impl_lower = impl_s.strip().lower()
        if impl_lower in _IMPL_STATUS_ALIAS:
            frontmatter["implementation_status"] = _IMPL_STATUS_ALIAS[impl_lower]
        elif impl_lower not in (
            "none",
            "planned",
            "in_progress",
            "partial",
            "implemented",
            "complete",
            "verified",
            "rolled_back",
        ):
            # Non-standard value: if contains 'complete' treat as partial/complete
            if "complete" in impl_lower:
                frontmatter["implementation_status"] = "partial"
            else:
                frontmatter["implementation_status"] = "in_progress"

    # C.5h — review_status: normalize known freetext patterns only
    rs = frontmatter.get("review_status")
    if isinstance(rs, str) and rs not in ("pending", "in_review", "approved", "rejected", "stale"):
        rs_lower = rs.strip().lower()
        if rs_lower in ("accepted", "approved"):
            frontmatter["review_status"] = "approved"
        elif "review" in rs_lower:
            frontmatter["review_status"] = "approved"  # 'reviewed — ...' / 'v1 reviewed' → approved
        elif rs_lower.startswith("pending"):
            frontmatter["review_status"] = "pending"
        elif rs_lower.startswith("stale"):
            frontmatter["review_status"] = "stale"
        # else: leave as-is — schema validation will reject truly invalid values

    # C.5i — implementation_done_when: if list, join to string
    idw = frontmatter.get("implementation_done_when")
    if isinstance(idw, list):
        frontmatter["implementation_done_when"] = "; ".join(str(x) for x in idw)

    # C.5j — version: coerce float to int
    ver = frontmatter.get("version")
    if isinstance(ver, float):
        frontmatter["version"] = int(ver)

    # C.5k — domains: fix pattern violations (must match ^[a-z][a-z0-9-]*(/...)$)
    doms = frontmatter.get("domains")
    if isinstance(doms, list):
        fixed = []
        for d in doms:
            if isinstance(d, str):
                d_clean = d.lower().replace(" ", "-").replace("_", "-")
                # Remove dots (e.g. schulungspass.de → schulungspass-de)
                d_clean = d_clean.replace(".", "-")
                if d_clean and d_clean[0].isalpha():
                    fixed.append(d_clean)
                else:
                    fixed.append("general")
            else:
                fixed.append(str(d))
        frontmatter["domains"] = fixed

    # C.6 — Amended-format normalization
    # If 'amended' is a plain date/string (legacy format), use it as
    # last_reviewed hint and drop the malformed field.
    amended_val = frontmatter.get("amended")
    if amended_val is not None and not isinstance(amended_val, list):
        if isinstance(amended_val, (str, datetime)):
            if "last_reviewed" not in frontmatter:
                frontmatter["last_reviewed"] = str(amended_val)[:10]  # YYYY-MM-DD
        # Always remove malformed amended (whether we used it or not)
        frontmatter.pop("amended", None)

    # C.7 — `implemented` field handling
    if "implemented" in frontmatter:
        val = frontmatter.pop("implemented")
        if frontmatter.get("implementation_status") in (None, "none"):
            if isinstance(val, bool) and val:
                frontmatter["implementation_status"] = "implemented"
            elif isinstance(val, (str, datetime)) and val:
                # Date when implemented — set status + record date in 'updated'
                frontmatter["implementation_status"] = "implemented"
                if "updated" not in frontmatter:
                    frontmatter["updated"] = str(val)[:10]
            # bool False or other → leave implementation_status unchanged

    # C.8 — Strip unknown/tool-specific properties
    for key in list(frontmatter.keys()):
        if key in _STRIPPED_FIELDS:
            frontmatter.pop(key)

    return frontmatter


def _registry(schemas_dir: Path) -> Registry:
    """Build a referencing Registry so cross-schema $refs resolve."""
    registry = Registry()
    for schema_file in schemas_dir.glob("*.json"):
        with open(schema_file) as f:
            schema = json.load(f)
        registry = registry.with_resource(
            uri=schema["$id"],
            resource=Resource.from_contents(schema),
        )
    return registry


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        # ISO 8601; fall back to date-only -> midnight UTC
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            pass
    if hasattr(value, "year") and hasattr(value, "month"):  # datetime.date
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise ADRLoadError(f"Cannot interpret {value!r} as datetime")


def _build_temporal(data: dict[str, Any], default_valid_from: datetime) -> TemporalRange:
    valid_from = _to_datetime(data["valid_from"]) if data.get("valid_from") else default_valid_from
    valid_to = _to_datetime(data["valid_to"]) if data.get("valid_to") else None
    knowledge_from = _to_datetime(data["knowledge_from"]) if data.get("knowledge_from") else valid_from
    return TemporalRange(
        valid_from=valid_from,
        valid_to=valid_to,
        knowledge_from=knowledge_from,
        retroactive=bool(data.get("retroactive", False)),
    )


def _build_scope(data: dict[str, Any] | None) -> Scope:
    data = data or {}
    return Scope(
        include_paths=tuple(data.get("include_paths", ())),
        exclude_paths=tuple(data.get("exclude_paths", ())),
        file_types=tuple(data.get("file_types", ())),
    )


_ADR_REF_RE = re.compile(r"(ADR-\d{3,5})")


def _normalize_refs(refs: list[Any] | str | None) -> tuple[str, ...]:
    """Normalize ADR references to canonical strings.
    Handles three input shapes (all observed in the wild):
      - list of strings: ['ADR-099', 'ADR-187§E3']
      - list of dicts: [{'id': 'ADR-099', 'reason': '...', 'section': 'E3'}]
      - plain string: 'ADR-110 (Legacy) — replaced' or 'ADR-099, ADR-188'

    Plain strings have all 'ADR-NNNN' tokens extracted (loses section suffix —
    that's a known limitation of freetext form, intentional).
    Object form preserves section as 'id§section'.
    """
    if not refs:
        return ()
    if isinstance(refs, str):
        # Freetext — extract every ADR-NNNN reference
        return tuple(m.group(1) for m in _ADR_REF_RE.finditer(refs))
    out: list[str] = []
    for r in refs:
        if isinstance(r, str):
            # Already canonical (e.g. 'ADR-187§E3') OR freetext like
            # 'ADR-057-platform-test-strategy.md' — extract the ADR-NNN core
            if re.match(r"^ADR-\d{3,5}(§[A-Za-z0-9_.-]+)?$", r):
                out.append(r)
            else:
                m = _ADR_REF_RE.search(r)
                if m:
                    out.append(m.group(1))
        elif isinstance(r, dict) and "id" in r:
            section = r.get("section")
            if section:
                out.append(f"{r['id']}§{section}")
            else:
                out.append(r["id"])
    return tuple(out)


def load_adr(
    md_path: Path,
    schemas_dir: Path,
    validate: bool = True,
    raw: bool = False,
) -> ADR:
    """Load a single ADR markdown file and its sibling .rules.yaml (if any).

    Args:
        md_path: Path to the ADR markdown file
        schemas_dir: Directory containing the JSON schemas
        validate: If True (default), run Phase 2 schema validation
        raw: If True, skip Phase 1 normalization (for diagnostic purposes —
             see what the loader sees BEFORE any aliases or transforms).
             Useful for finding ADRs that rely on tolerance.

    Default behavior (validate=True, raw=False):
      Phase 1 normalize → Phase 2 validate → Phase 3 construct domain object

    Schema v3 design: normalization is the default, no `lenient` flag needed.
    """
    # Reject symlinks that escape the ADR directory (e.g. ADR-x.md -> /etc/secret)
    # before reading anything off disk.
    _require_within(md_path, md_path.parent, "ADR file")
    md_text = md_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(md_text)
    if not m:
        raise ADRLoadError(f"{md_path}: missing YAML frontmatter")
    frontmatter = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)

    # Phase 1 — Normalize (Schema v3 C.1-C.8). Skipped only if raw=True.
    if not raw:
        frontmatter = _normalize_frontmatter(frontmatter, body, md_path)

    if validate:
        registry = _registry(schemas_dir)
        with open(schemas_dir / "adr_frontmatter.schema.json") as f:
            fm_schema = json.load(f)
        validator = Draft202012Validator(fm_schema, registry=registry)
        errors = sorted(validator.iter_errors(frontmatter), key=lambda e: list(e.path))
        if errors:
            messages = []
            for err in errors:
                loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
                messages.append(f"  {loc}: {err.message}")
            raise ADRLoadError(f"{md_path}: frontmatter validation failed:\n" + "\n".join(messages))

    decision_date = _to_datetime(frontmatter["decision_date"])
    temporal = _build_temporal(frontmatter, default_valid_from=decision_date)

    rules: list[Rule] = []
    rules_filename = frontmatter.get("rules_file")
    if rules_filename:
        # rules_file is a free-form frontmatter string; constrain it to a bare
        # filename beside the ADR (no separators / absolute / '..') and verify
        # containment after resolution (catches a rules_file that is itself a
        # symlink pointing outside the directory).
        if Path(rules_filename).name != rules_filename:
            raise ADRLoadError(f"{md_path}: rules_file must be a bare filename beside the ADR, got {rules_filename!r}")
        rules_path = _require_within(md_path.parent / rules_filename, md_path.parent, "rules_file")
        if rules_path.exists():
            rules = _load_rules(
                rules_path,
                adr_id=frontmatter["id"],
                adr_temporal=temporal,
                schemas_dir=schemas_dir,
                validate=validate,
            )

    # v1.1 fields
    amendments = tuple(
        Amendment(
            version=a["version"],
            at=_to_datetime(a["at"]),
            by=a["by"],
            summary=a["summary"],
            sections_changed=tuple(a.get("sections_changed", ())),
            rationale=a.get("rationale", ""),
        )
        for a in frontmatter.get("amended", [])
    )
    decision_drivers = tuple(
        DecisionDriver(
            id=d["id"],
            driver=d["driver"],
            weight=d["weight"],
            category=d.get("category"),
        )
        for d in frontmatter.get("decision_drivers", [])
    )
    open_questions = tuple(
        OpenQuestion(
            id=q["id"],
            question=q["question"],
            decide_by=q.get("decide_by"),
            owner=q.get("owner"),
            status=q.get("status", "open"),
            resolution=q.get("resolution"),
        )
        for q in frontmatter.get("open_questions", [])
    )
    deprecation_timeline = tuple(
        DeprecationStep(
            phase=p["phase"],
            action=p["action"],
            state=p["state"],
            earliest=p.get("earliest"),
            completion_signal=p.get("completion_signal", ""),
        )
        for p in frontmatter.get("deprecation_timeline", [])
    )
    spof_mitigation = tuple(
        SPOFMitigation(
            component=s["component"],
            measure=s["measure"],
            implementation=s.get("implementation", ""),
            phase=s.get("phase"),
        )
        for s in frontmatter.get("spof_mitigation", [])
    )
    per_repo: list[PerRepoStatus] = []
    for repo_name, prs in (frontmatter.get("per_repo_status") or {}).items():
        per_repo.append(
            PerRepoStatus(
                repo=repo_name,
                status=Status(prs["status"]) if "status" in prs else None,
                implementation_status=prs.get("implementation_status", "none"),
                planned_phase=str(prs["planned_phase"]) if prs.get("planned_phase") is not None else None,
                target_date=_to_datetime(prs["target_date"]) if prs.get("target_date") else None,
                actual_completion_date=_to_datetime(prs["actual_completion_date"])
                if prs.get("actual_completion_date")
                else None,
                notes=prs.get("notes", ""),
            )
        )

    adr = ADR(
        id=frontmatter["id"],
        title=frontmatter["title"],
        status=Status(frontmatter["status"]),
        domains=tuple(frontmatter["domains"]),
        deciders=tuple(frontmatter["deciders"]),
        decision_date=decision_date,
        temporal=temporal,
        rationale_summary=frontmatter.get("rationale_summary", "") or "",
        supersedes=_normalize_refs(frontmatter.get("supersedes")),
        superseded_by=_normalize_refs(frontmatter.get("superseded_by")),
        consolidates=_normalize_refs(frontmatter.get("consolidates")),
        depends_on=_normalize_refs(frontmatter.get("depends_on")),
        conflicts_with=_normalize_refs(frontmatter.get("conflicts_with")),
        rules=rules,
        raw_frontmatter=frontmatter,
        body_markdown=body,
        amendments=amendments,
        decision_drivers=decision_drivers,
        open_questions=open_questions,
        deprecation_timeline=deprecation_timeline,
        spof_mitigation=spof_mitigation,
        per_repo_status=tuple(per_repo),
        repo=frontmatter.get("repo"),
        consumers=tuple(frontmatter.get("consumers", ())),
        implementation_status=frontmatter.get("implementation_status", "none"),
        staleness_months=frontmatter.get("staleness_months"),
        drift_check_paths=tuple(frontmatter.get("drift_check_paths", ())),
        updated=_to_datetime(frontmatter["updated"]) if frontmatter.get("updated") else None,
        version=frontmatter.get("version"),
        review_status=frontmatter.get("review_status"),
        owner=frontmatter.get("owner"),
        implementation_done_when=frontmatter.get("implementation_done_when"),
    )
    return adr


def _load_rules(
    rules_path: Path,
    adr_id: str,
    adr_temporal: TemporalRange,
    schemas_dir: Path,
    validate: bool,
) -> list[Rule]:
    with open(rules_path) as f:
        doc = yaml.safe_load(f)

    if validate:
        registry = _registry(schemas_dir)
        with open(schemas_dir / "adr_rules.schema.json") as f:
            rules_schema = json.load(f)
        validator = Draft202012Validator(rules_schema, registry=registry)
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            messages = []
            for err in errors:
                loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
                messages.append(f"  {loc}: {err.message}")
            raise ADRLoadError(f"{rules_path}: rules validation failed:\n" + "\n".join(messages))

    if doc.get("adr_id") != adr_id:
        raise ADRLoadError(f"{rules_path}: adr_id {doc.get('adr_id')!r} does not match parent ADR {adr_id!r}")

    default_severity = Severity(doc.get("default_severity", "warning"))

    rules: list[Rule] = []
    for r in doc["rules"]:
        rule_temporal = _build_temporal(r, default_valid_from=adr_temporal.valid_from)
        rule_scope = _build_scope(r.get("applies_to"))
        rules.append(
            Rule(
                adr_id=adr_id,
                rule_id=r["id"],
                title=r["title"],
                severity=Severity(r.get("severity", default_severity)),
                rationale=r["rationale"],
                temporal=rule_temporal,
                scope=rule_scope,
                checker_spec=r["checker"],
                fix_suggestions=r.get("fix_suggestions", []),
                audience_explanations=r.get("audience_explanations", {}),
                blast_radius=r.get("blast_radius_estimator"),
                examples=r.get("examples", {}),
            )
        )
    return rules


def load_adrs(adrs_dir: Path, schemas_dir: Path, validate: bool = True, raw: bool = False) -> list[ADR]:
    """Load every ADR in a directory. See load_adr for the meaning of raw."""
    adrs: list[ADR] = []
    for md_path in sorted(adrs_dir.glob("ADR-*.md")):
        if md_path.name.startswith("ADR-") and md_path.suffix == ".md":
            adrs.append(load_adr(md_path, schemas_dir, validate=validate, raw=raw))
    return adrs
