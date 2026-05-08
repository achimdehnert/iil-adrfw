"""Validate all example ADRs against the schemas."""
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

base = Path("/home/claude/iil-adrfw")
schemas_dir = base / "schemas"
examples_dir = base / "examples"

registry = Registry()
for schema_file in schemas_dir.glob("*.json"):
    with open(schema_file) as f:
        schema = json.load(f)
    registry = registry.with_resource(
        uri=schema["$id"],
        resource=Resource.from_contents(schema),
    )

with open(schemas_dir / "adr_frontmatter.schema.json") as f:
    fm_schema = json.load(f)
with open(schemas_dir / "adr_rules.schema.json") as f:
    rules_schema = json.load(f)

fm_validator = Draft202012Validator(fm_schema, registry=registry)
rules_validator = Draft202012Validator(rules_schema, registry=registry)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def validate_adr(md_path: Path) -> bool:
    print(f"\n--- {md_path.name} ---")
    md_text = md_path.read_text()
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        print("  FAIL  no frontmatter")
        return False
    frontmatter = yaml.safe_load(m.group(1))

    fm_errors = sorted(fm_validator.iter_errors(frontmatter), key=lambda e: list(e.path))
    if fm_errors:
        print(f"  FAIL  frontmatter ({len(fm_errors)} errors):")
        for err in fm_errors[:10]:
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"    {loc}: {err.message[:200]}")
        return False
    print(f"  OK    frontmatter ({len(frontmatter)} top-level keys)")

    rules_filename = frontmatter.get("rules_file")
    if rules_filename:
        rules_path = md_path.parent / rules_filename
        if not rules_path.exists():
            print(f"  FAIL  rules_file {rules_filename!r} not found")
            return False
        rules_doc = yaml.safe_load(rules_path.read_text())
        rules_errors = sorted(rules_validator.iter_errors(rules_doc), key=lambda e: list(e.path))
        if rules_errors:
            print(f"  FAIL  rules ({len(rules_errors)} errors):")
            for err in rules_errors[:10]:
                loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
                print(f"    {loc}: {err.message[:200]}")
            return False
        print(f"  OK    rules ({len(rules_doc['rules'])} rules)")

        if rules_doc["adr_id"] != frontmatter["id"]:
            print(f"  FAIL  rules.adr_id mismatch")
            return False

    if "amended" in frontmatter:
        print(f"  >>    amended: {len(frontmatter['amended'])} revision(s)")
    if "decision_drivers" in frontmatter:
        weights = [d["weight"] for d in frontmatter["decision_drivers"]]
        print(f"  >>    decision_drivers: {len(frontmatter['decision_drivers'])} ({weights.count('critical')} critical)")
    if "open_questions" in frontmatter:
        print(f"  >>    open_questions: {len(frontmatter['open_questions'])} open")
    if "deprecation_timeline" in frontmatter:
        print(f"  >>    deprecation_timeline: {len(frontmatter['deprecation_timeline'])} phases")
    if "spof_mitigation" in frontmatter:
        print(f"  >>    spof_mitigation: {len(frontmatter['spof_mitigation'])} mitigations")
    if "consolidates" in frontmatter:
        print(f"  >>    consolidates: {len(frontmatter['consolidates'])} ADRs")
    if "per_repo_status" in frontmatter:
        repos = list(frontmatter["per_repo_status"].keys())
        print(f"  >>    per_repo_status: {len(repos)} repos")
    return True


all_ok = True
for md_file in sorted(examples_dir.glob("ADR-*.md")):
    if not validate_adr(md_file):
        all_ok = False

print()
print("=" * 60)
if all_ok:
    print("ALL ADRs VALIDATE")
else:
    print("VALIDATION FAILURES")
    sys.exit(1)
