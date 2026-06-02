"""Render an ADR index table in the platform `INDEX.md` format.

Produces the table block (and optional header/footer) used by `platform/docs/adr/INDEX.md`:

    | # | Title | Status | Impl | Link |
    |---|-------|--------|------|------|
    | 007 | Tenant- & RBAC-Architektur ... | `Accepted` | ✅ | [ADR-007](ADR-007-FINAL-PRODUCTION.md) |

Reads YAML frontmatter directly (no full schema validation) so archived ADRs
with non-standard `status: moved` and other drift cases still render.

Impl-emoji mapping follows ADR-138 (Implementation Tracking Standard).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
_TITLE_PREFIX_RE = re.compile(r"^ADR-\d+(?:\s+[A-Z]+)?\s*[:—–-]\s*", re.UNICODE)
_FILENAME_RE = re.compile(r"^ADR-(\d{3,5})", re.IGNORECASE)

# ADR-138 Impl emoji map. Values not in the map render as the literal value
# in backticks so drift is visible rather than silently hidden.
_IMPL_EMOJI = {
    "none": "⬜",
    "partial": "🔶",
    "implemented": "✅",
    "verified": "✅✅",
}

# Statuses where impl tracking does not apply (per ADR-138).
_INACTIVE_STATUSES = {"deprecated", "superseded", "rejected", "void", "archived", "moved"}


def _read_frontmatter(md_path: Path) -> tuple[dict, str]:
    text = md_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, m.group(2)


def _resolve_id(fm: dict, md_path: Path) -> str | None:
    raw_id = fm.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    m = _FILENAME_RE.match(md_path.stem)
    if m:
        return f"ADR-{m.group(1)}"
    return None


def _resolve_title(fm: dict, body: str, md_path: Path) -> str:
    title = fm.get("title")
    if isinstance(title, str) and title.strip():
        return _strip_id_prefix(title.strip())
    h1 = _H1_RE.search(body or "")
    if h1:
        return _strip_id_prefix(h1.group(1).strip())
    stem = md_path.stem
    slug = re.sub(r"^ADR-\d+-", "", stem).replace("-", " ").replace("_", " ")
    return slug or "(untitled)"


def _strip_id_prefix(title: str) -> str:
    """Drop leading `ADR-NNN [QUALIFIER]: ` so the `#` column stays the only ID source."""
    return _TITLE_PREFIX_RE.sub("", title).strip() or title


def _resolve_status(fm: dict, md_path: Path) -> str:
    if "_archive" in md_path.parts:
        return "archived"
    raw = fm.get("status")
    if isinstance(raw, str):
        s = raw.strip().strip('"').strip("'").lower()
        return s or "unknown"
    return "unknown"


def _impl_cell(status: str, impl: str | None) -> str:
    if status in _INACTIVE_STATUSES:
        return "—"
    if impl is None or not str(impl).strip():
        return _IMPL_EMOJI["none"]
    key = str(impl).strip().lower()
    return _IMPL_EMOJI.get(key, f"`{key}`")


def _format_status(status: str) -> str:
    return f"`{status.capitalize()}`" if status else "`Unknown`"


def _id_number(adr_id: str) -> str:
    m = _FILENAME_RE.match(adr_id)
    return m.group(1) if m else adr_id


def _live_md_files(adr_dir: Path) -> list[Path]:
    return sorted(adr_dir.glob("ADR-*.md"))


def _archive_md_files(adr_dir: Path) -> list[Path]:
    """Return archived ADR files.

    Preferred convention: `_archive/superseded/ADR-*.md`. Falls back to
    direct children of `_archive/` for repos that don't use the subfolder.
    `_archive/reviews/` and similar non-ADR subtrees are intentionally
    excluded — they hold review notes, not ADRs.
    """
    archive = adr_dir / "_archive"
    if not archive.is_dir():
        return []
    superseded = archive / "superseded"
    if superseded.is_dir():
        return sorted(superseded.glob("ADR-*.md"))
    return sorted(archive.glob("ADR-*.md"))


def _row_from_md(md: Path, adr_dir: Path) -> dict | None:
    fm, body = _read_frontmatter(md)
    adr_id = _resolve_id(fm, md)
    if not adr_id:
        return None
    status = _resolve_status(fm, md)
    impl = fm.get("implementation_status")
    title = _resolve_title(fm, body, md)
    link = md.relative_to(adr_dir).as_posix()
    return {
        "id": adr_id,
        "num": _id_number(adr_id),
        "title": title,
        "status": status,
        "impl": _impl_cell(status, impl),
        "link": link,
    }


def render_index(
    adr_dir: Path,
    *,
    include_archive: bool = False,
    include_header: bool = True,
    next_free: int | None = None,
) -> str:
    """Render the ADR index as Markdown.

    With include_header=True, emits the same H1+legend+next-free preamble that
    the platform INDEX.md uses. With include_header=False, emits only the
    table block — suitable for splicing into an existing INDEX.md between
    marker comments.

    Live ADRs (direct children of adr_dir) are always scanned. With
    include_archive=True, ADR-*.md files under adr_dir/_archive are added only
    if their number does not collide with a live ADR (archive files with
    duplicated numbers predate the unified numbering scheme).
    """
    live_rows: list[dict] = []
    for md in _live_md_files(adr_dir):
        row = _row_from_md(md, adr_dir)
        if row:
            live_rows.append(row)

    live_nums = {r["num"] for r in live_rows}

    archive_rows: list[dict] = []
    if include_archive:
        for md in _archive_md_files(adr_dir):
            row = _row_from_md(md, adr_dir)
            if row and row["num"] not in live_nums:
                archive_rows.append(row)

    rows = sorted(live_rows + archive_rows, key=lambda r: r["num"])

    if next_free is None:
        live_numeric = [int(r["num"]) for r in live_rows if r["num"].isdigit()]
        next_free = max(live_numeric) + 1 if live_numeric else None

    lines: list[str] = []
    if include_header:
        lines += [
            "# Architecture Decision Records -- Index",
            "",
            f"> **Last updated:** {date.today().isoformat()}",
        ]
        if next_free is not None:
            lines.append(f"> **Next free ADR number:** {next_free}")
        lines += [
            "",
            "## Legend",
            "",
            "| Status | Bedeutung |",
            "|--------|-----------|",
            "| `Proposed` | Vorgeschlagen, noch nicht akzeptiert |",
            "| `Accepted` | Akzeptiert und gueltig |",
            "| `Deprecated` | Veraltet, ersetzt durch neueres ADR |",
            "| `Superseded` | Vollstaendig ersetzt |",
            "| `Archived` | In `_archive/superseded/` verschoben -- nicht mehr aktiv |",
            "",
            "### Impl Column (ADR-138)",
            "",
            "| Emoji | Meaning |",
            "|-------|---------|",
            "| — | Not applicable (deprecated/superseded/archived) |",
            "| ⬜ | `none` — not started |",
            "| 🔶 | `partial` — in progress |",
            "| ✅ | `implemented` |",
            "| ✅✅ | `verified` in production |",
            "",
            "## ADR Index",
            "",
            f"> Auto-generated by `iil-adrfw index` on {date.today().isoformat()}.",
            f"> Total: **{len(rows)} ADRs**",
            "",
        ]

    lines += [
        "| # | Title | Status | Impl | Link |",
        "|---|-------|--------|------|------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['num']} | {r['title']} | {_format_status(r['status'])} | {r['impl']} | [{r['id']}]({r['link']}) |"
        )

    return "\n".join(lines) + "\n"
