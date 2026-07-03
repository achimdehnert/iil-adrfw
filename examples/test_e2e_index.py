"""Tests for iil_adrfw.index — INDEX.md rendering (ADR-138 Impl column, archive handling)."""

from pathlib import Path

from iil_adrfw.index import render_index


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _adr_dir(tmp_path: Path) -> Path:
    _write(
        tmp_path / "ADR-007-tenant.md",
        "---\nid: ADR-007\ntitle: 'ADR-007: Tenant architecture'\nstatus: accepted\n"
        "implementation_status: implemented\n---\n\n# ADR-007: Tenant architecture\n",
    )
    _write(
        tmp_path / "ADR-010-partial.md",
        "---\nid: ADR-010\ntitle: Partial thing\nstatus: proposed\nimplementation_status: partial\n---\nbody\n",
    )
    _write(
        tmp_path / "ADR-012-superseded.md",
        "---\nid: ADR-012\ntitle: Old approach\nstatus: superseded\nimplementation_status: implemented\n---\nbody\n",
    )
    # No frontmatter → id from filename, title from H1
    _write(tmp_path / "ADR-020-no-frontmatter.md", "# ADR-020 — Title from heading\n\nBody.\n")
    return tmp_path


def test_should_render_table_with_impl_emojis_and_sorted_rows(tmp_path):
    out = render_index(_adr_dir(tmp_path), include_header=False)
    lines = [ln for ln in out.splitlines() if ln.startswith("| ") and "---" not in ln]
    # header row + 4 ADRs, sorted by number
    assert lines[0].startswith("| # | Title |")
    assert [ln.split("|")[1].strip() for ln in lines[1:]] == ["007", "010", "012", "020"]
    assert "| 007 | Tenant architecture | `Accepted` | ✅ | [ADR-007](ADR-007-tenant.md) |" in out
    assert "🔶" in out  # partial
    assert "| 012 | Old approach | `Superseded` | — |" in out  # inactive → no impl tracking
    assert "Title from heading" in out


def test_should_emit_header_with_next_free_number(tmp_path):
    out = render_index(_adr_dir(tmp_path), include_header=True)
    assert out.startswith("# Architecture Decision Records -- Index")
    assert "**Next free ADR number:** 21" in out
    assert "Total: **4 ADRs**" in out
    assert "## Legend" in out


def test_should_render_unknown_impl_value_verbatim_so_drift_is_visible(tmp_path):
    _write(
        tmp_path / "ADR-030-drift.md",
        "---\nid: ADR-030\ntitle: Drifted\nstatus: accepted\nimplementation_status: wip\n---\nbody\n",
    )
    out = render_index(tmp_path, include_header=False)
    assert "`wip`" in out


def test_should_default_impl_to_none_emoji_for_active_adr_without_field(tmp_path):
    _write(tmp_path / "ADR-031-bare.md", "---\nid: ADR-031\ntitle: Bare\nstatus: accepted\n---\nbody\n")
    out = render_index(tmp_path, include_header=False)
    assert "⬜" in out


def test_should_include_archive_rows_unless_number_collides_with_live(tmp_path):
    adr_dir = _adr_dir(tmp_path)
    # Colliding number (007) → skipped; unique number (005) → included as archived
    _write(
        adr_dir / "_archive" / "superseded" / "ADR-007-old.md",
        "---\nid: ADR-007\ntitle: Old tenant\nstatus: moved\n---\nbody\n",
    )
    _write(
        adr_dir / "_archive" / "superseded" / "ADR-005-ancient.md",
        "---\nid: ADR-005\ntitle: Ancient decision\nstatus: superseded\n---\nbody\n",
    )
    out = render_index(adr_dir, include_header=False, include_archive=True)
    assert "| 005 | Ancient decision | `Archived` | — | [ADR-005](_archive/superseded/ADR-005-ancient.md) |" in out
    assert "Old tenant" not in out  # collision with live ADR-007

    # Without include_archive, archived rows never appear
    out_live = render_index(adr_dir, include_header=False)
    assert "Ancient decision" not in out_live


def test_should_fall_back_to_direct_archive_children_without_superseded_dir(tmp_path):
    _write(tmp_path / "ADR-001-live.md", "---\nid: ADR-001\ntitle: Live\nstatus: accepted\n---\nbody\n")
    _write(tmp_path / "_archive" / "ADR-002-flat.md", "---\nid: ADR-002\ntitle: Flat archive\nstatus: moved\n---\nx\n")
    out = render_index(tmp_path, include_header=False, include_archive=True)
    assert "Flat archive" in out


def test_should_survive_broken_frontmatter_and_untitled_files(tmp_path):
    _write(tmp_path / "ADR-040-broken.md", "---\n: not: [valid yaml\n---\nbody without heading\n")
    out = render_index(tmp_path, include_header=False)
    # id resolved from filename, title from slug, status unknown
    assert "| 040 | broken | `Unknown` |" in out


# ─── CLI subcommand: iil-adrfw index (issue #43) ─────────────────


def test_should_render_index_via_cli_subcommand(tmp_path, capsys):
    import argparse

    import iil_adrfw.cli as cli

    _write(
        tmp_path / "ADR-007-tenant.md",
        "---\nid: ADR-007\ntitle: Tenant architecture\nstatus: accepted\n"
        "implementation_status: implemented\n---\n\n# ADR-007\n",
    )
    args = argparse.Namespace(adr_dir=str(tmp_path), include_archive=False, table_only=True, output=None)
    assert cli._cmd_index(args) == 0
    out = capsys.readouterr().out
    assert out.startswith("| # | Title | Status | Impl | Link |")
    assert "| 007 | Tenant architecture | `Accepted` | ✅ | [ADR-007](ADR-007-tenant.md) |" in out


def test_should_write_index_to_output_file_and_include_header(tmp_path, capsys):
    import argparse

    import iil_adrfw.cli as cli

    _write(tmp_path / "ADR-001-x.md", "---\nid: ADR-001\ntitle: X\nstatus: accepted\n---\nbody\n")
    out_file = tmp_path / "INDEX.md"
    args = argparse.Namespace(adr_dir=str(tmp_path), include_archive=False, table_only=False, output=str(out_file))
    assert cli._cmd_index(args) == 0
    assert "Wrote INDEX" in capsys.readouterr().out
    written = out_file.read_text(encoding="utf-8")
    assert written.startswith("# Architecture Decision Records -- Index")
    assert "| 001 | X |" in written


def test_should_exit_2_when_index_adr_dir_missing(tmp_path, capsys):
    import argparse

    import iil_adrfw.cli as cli

    args = argparse.Namespace(adr_dir=str(tmp_path / "nope"), include_archive=False, table_only=True, output=None)
    assert cli._cmd_index(args) == 2
    assert "is not a directory" in capsys.readouterr().err
