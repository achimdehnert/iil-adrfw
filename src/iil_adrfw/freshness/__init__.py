"""Content freshness checker — validate ADR textual claims against system state.

Architecture:
- Phase 1: Deterministic claim extraction (regex-based)
  - Version claims: "PostgreSQL 14", "Redis 7", "Python 3.12"
  - Port claims: "port 8085", "8000/tcp"
  - Tool claims: "gunicorn", "celery", "nginx"
  - Image claims: "python:3.12-slim", "postgres:16"
- Phase 2: Reality comparison against compose/requirements files
- Phase 3 (future): LLM-assisted for complex architectural claims

No LLM calls in Phase 1+2. Deterministic and fast.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --- Claim types ---


@dataclass(frozen=True)
class Claim:
    """A factual assertion extracted from an ADR body."""
    adr_id: str
    claim_type: str  # 'version', 'port', 'image', 'tool'
    subject: str     # e.g. 'PostgreSQL', 'Redis', 'python'
    value: str       # e.g. '14', '8085', '3.12-slim'
    source_line: str  # the line it was extracted from (for debugging)


@dataclass(frozen=True)
class FreshnessFinding:
    """A claim that doesn't match reality."""
    adr_id: str
    claim: Claim
    actual_value: str
    source_file: str  # where the actual value was found
    severity: str = "warning"  # 'info' | 'warning' | 'error'

    @property
    def description(self) -> str:
        return (
            f"{self.adr_id} claims {self.claim.subject} {self.claim.value}, "
            f"but {self.source_file} shows {self.actual_value}"
        )


@dataclass
class FreshnessReport:
    """Full output of the freshness check."""
    total_claims: int = 0
    stale_claims: list[FreshnessFinding] = field(default_factory=list)
    verified_claims: int = 0
    unverifiable_claims: int = 0
    runtime_ms: int = 0


# --- Claim extraction (Phase 1) ---


# Patterns for version extraction from markdown text
_VERSION_PATTERNS = [
    # "PostgreSQL 16", "Redis 7.2", "Python 3.12"
    re.compile(
        r"\b(PostgreSQL|Postgres|Redis|Python|Django|Celery|Gunicorn|Nginx|Node|npm|"
        r"Docker|Compose|FastAPI|Flask|React|Vue|Angular|Svelte|"
        r"Ubuntu|Debian|Alpine)\s+v?(\d+(?:\.\d+){0,2})\b",
        re.IGNORECASE
    ),
    # "pg16", "py3.12"
    re.compile(
        r"\b(pg|py|node)(\d+(?:\.\d+){0,2})\b",
        re.IGNORECASE
    ),
]

# Docker image patterns: "python:3.12-slim", "postgres:16", "redis:7-alpine"
_IMAGE_PATTERN = re.compile(
    r"\b(python|postgres|redis|node|nginx|alpine|ubuntu|debian|pgvector/pgvector)"
    r":(\d+(?:\.\d+){0,2}(?:-[a-z0-9]+)?)\b",
    re.IGNORECASE
)

# Port patterns: "port 8085", ":8085", "8000/tcp"
_PORT_PATTERN = re.compile(
    r"(?:port\s+|:)(\d{4,5})(?:/tcp|/udp)?\b|\b(\d{4,5})(?:/tcp|/udp)\b",
    re.IGNORECASE
)

# Abbreviation normalization
_SUBJECT_NORMALIZE = {
    "pg": "PostgreSQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "py": "Python",
    "python": "Python",
    "node": "Node.js",
    "redis": "Redis",
    "django": "Django",
    "celery": "Celery",
    "gunicorn": "Gunicorn",
    "nginx": "Nginx",
    "docker": "Docker",
    "compose": "Docker Compose",
    "pgvector/pgvector": "pgvector",
}


def _normalize_subject(raw: str) -> str:
    return _SUBJECT_NORMALIZE.get(raw.lower(), raw)


def extract_claims(adr_id: str, body: str) -> list[Claim]:
    """Extract factual claims from ADR markdown body. Deterministic, no LLM."""
    claims: list[Claim] = []
    seen: set[tuple[str, str, str]] = set()  # (type, subject, value)

    for line in body.splitlines():
        # Skip markdown headers and code block markers
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("```"):
            continue

        # Version claims
        for pattern in _VERSION_PATTERNS:
            for m in pattern.finditer(line):
                subject = _normalize_subject(m.group(1))
                value = m.group(2)
                key = ("version", subject, value)
                if key not in seen:
                    seen.add(key)
                    claims.append(Claim(
                        adr_id=adr_id,
                        claim_type="version",
                        subject=subject,
                        value=value,
                        source_line=stripped[:120],
                    ))

        # Docker image claims
        for m in _IMAGE_PATTERN.finditer(line):
            subject = _normalize_subject(m.group(1))
            value = m.group(2)
            key = ("image", subject, value)
            if key not in seen:
                seen.add(key)
                claims.append(Claim(
                    adr_id=adr_id,
                    claim_type="image",
                    subject=subject,
                    value=value,
                    source_line=stripped[:120],
                ))

        # Port claims
        for m in _PORT_PATTERN.finditer(line):
            port = m.group(1) or m.group(2)
            key = ("port", "service", port)
            if key not in seen:
                seen.add(key)
                claims.append(Claim(
                    adr_id=adr_id,
                    claim_type="port",
                    subject="service",
                    value=port,
                    source_line=stripped[:120],
                ))

    return claims


# --- Reality extraction (Phase 2) ---


def _extract_versions_from_compose(compose_path: Path) -> dict[str, str]:
    """Extract image versions from docker-compose YAML."""
    versions: dict[str, str] = {}
    try:
        text = compose_path.read_text()
    except (FileNotFoundError, PermissionError):
        return versions

    for m in _IMAGE_PATTERN.finditer(text):
        subject = _normalize_subject(m.group(1))
        version = m.group(2)
        # Keep the latest/longest version found
        if subject not in versions or len(version) > len(versions[subject]):
            versions[subject] = version
    return versions


def _extract_versions_from_requirements(req_path: Path) -> dict[str, str]:
    """Extract package versions from requirements.txt or pyproject.toml."""
    versions: dict[str, str] = {}
    try:
        text = req_path.read_text()
    except (FileNotFoundError, PermissionError):
        return versions

    # requirements.txt: Django==5.1.2, redis>=7.0
    req_pattern = re.compile(r"^([a-zA-Z0-9_-]+)\s*[><=!~]+\s*(\d+(?:\.\d+){0,2})")
    for line in text.splitlines():
        m = req_pattern.match(line.strip())
        if m:
            pkg = _normalize_subject(m.group(1))
            versions[pkg] = m.group(2)

    # pyproject.toml: "Django>=5.1", "redis>=7.0"
    pyproject_pattern = re.compile(r'"([a-zA-Z0-9_-]+)\s*[><=!~]+\s*(\d+(?:\.\d+){0,2})')
    for m in pyproject_pattern.finditer(text):
        pkg = _normalize_subject(m.group(1))
        if pkg not in versions:
            versions[pkg] = m.group(2)

    return versions


def _extract_ports_from_compose(compose_path: Path) -> set[str]:
    """Extract exposed ports from docker-compose."""
    ports: set[str] = set()
    try:
        text = compose_path.read_text()
    except (FileNotFoundError, PermissionError):
        return ports

    # Match "8085:8000", "- 8085:8000"
    port_pattern = re.compile(r"(\d{4,5}):\d{4,5}")
    for m in port_pattern.finditer(text):
        ports.add(m.group(1))
    return ports


# --- Comparison (Phase 2) ---


def check_freshness(
    claims: list[Claim],
    repo_root: Path,
    compose_files: list[str] | None = None,
    requirements_files: list[str] | None = None,
) -> FreshnessReport:
    """Compare extracted claims against actual files in repo_root.

    Returns a FreshnessReport with stale_claims for each mismatch.
    """
    import time
    start = time.monotonic()

    if compose_files is None:
        compose_files = ["docker-compose.prod.yml", "docker-compose.yml"]
    if requirements_files is None:
        requirements_files = ["requirements.txt", "pyproject.toml"]

    # Gather reality
    reality_versions: dict[str, str] = {}
    reality_ports: set[str] = set()

    for cf in compose_files:
        p = repo_root / cf
        if p.exists():
            reality_versions.update(_extract_versions_from_compose(p))
            reality_ports.update(_extract_ports_from_compose(p))

    for rf in requirements_files:
        p = repo_root / rf
        if p.exists():
            reality_versions.update(_extract_versions_from_requirements(p))

    # Compare
    report = FreshnessReport(total_claims=len(claims))
    for claim in claims:
        if claim.claim_type in ("version", "image"):
            actual = reality_versions.get(claim.subject)
            if actual is None:
                report.unverifiable_claims += 1
            elif not actual.startswith(claim.value) and claim.value != actual:
                # Major version mismatch = warning, minor = info
                claim_major = claim.value.split(".")[0]
                actual_major = actual.split(".")[0]
                severity = "warning" if claim_major != actual_major else "info"
                report.stale_claims.append(FreshnessFinding(
                    adr_id=claim.adr_id,
                    claim=claim,
                    actual_value=actual,
                    source_file=str(repo_root),
                    severity=severity,
                ))
            else:
                report.verified_claims += 1
        elif claim.claim_type == "port":
            if reality_ports:
                if claim.value not in reality_ports:
                    report.stale_claims.append(FreshnessFinding(
                        adr_id=claim.adr_id,
                        claim=claim,
                        actual_value=f"ports found: {sorted(reality_ports)}",
                        source_file=str(repo_root),
                        severity="info",
                    ))
                else:
                    report.verified_claims += 1
            else:
                report.unverifiable_claims += 1
        else:
            report.unverifiable_claims += 1

    report.runtime_ms = int((time.monotonic() - start) * 1000)
    return report


# --- Top-level convenience ---


def check_adr_freshness(
    adr_id: str,
    body: str,
    repo_root: Path,
    compose_files: list[str] | None = None,
    requirements_files: list[str] | None = None,
) -> FreshnessReport:
    """Extract claims from ADR body and check against repo reality."""
    claims = extract_claims(adr_id, body)
    return check_freshness(claims, repo_root, compose_files, requirements_files)
