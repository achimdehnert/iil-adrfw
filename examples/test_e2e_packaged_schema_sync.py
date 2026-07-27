"""Guards against schemas/ (repo-root) drifting from the packaged copy
src/iil_adrfw/schemas/ that get_schema_dir() actually resolves to at
runtime for a pip-installed CLI.

Regression for: commit 6218675 (#59) added class/conforms_to/sunset_after/
extension_review_required/sister_of to schemas/adr_frontmatter.schema.json
only — the packaged copy stayed on the old, stricter schema. Every fix
landed on main and even shipped as a PyPI release (0.7.1) while
`iil-adrfw validate` kept rejecting the exact frontmatter it claimed to
support, because the CLI reads get_schema_dir(), not the repo-root copy
(illustration-hub#78).
"""

from __future__ import annotations

from pathlib import Path

from iil_adrfw.schemas import get_schema_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_SCHEMAS_DIR = REPO_ROOT / "schemas"


def test_should_keep_packaged_schemas_in_sync_with_repo_root():
    packaged_dir = get_schema_dir()
    root_files = sorted(p.name for p in ROOT_SCHEMAS_DIR.glob("*.schema.json"))
    packaged_files = sorted(p.name for p in packaged_dir.glob("*.schema.json"))
    assert root_files == packaged_files, (
        f"schemas/ and {packaged_dir} list different files — root={root_files} packaged={packaged_files}"
    )

    for name in root_files:
        root_content = (ROOT_SCHEMAS_DIR / name).read_text(encoding="utf-8")
        packaged_content = (packaged_dir / name).read_text(encoding="utf-8")
        assert root_content == packaged_content, (
            f"{name} differs between schemas/ (repo-root, used by dev checkouts) "
            f"and {packaged_dir} (bundled into the wheel/sdist, used by "
            f"get_schema_dir() at runtime) — a fix applied to only one of them "
            f"ships broken. Copy schemas/{name} over the packaged copy."
        )
    print("  PASS: schemas/ and packaged src/iil_adrfw/schemas/ are byte-identical")


if __name__ == "__main__":
    test_should_keep_packaged_schemas_in_sync_with_repo_root()
    print("=" * 70)
    print("ALL packaged_schema_sync TESTS PASSED")
    print("=" * 70)
