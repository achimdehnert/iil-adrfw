"""Validate that the three schemas themselves are valid JSON Schema 2020-12."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schemas_dir = Path("/home/claude/iil-adrfw/schemas")
for schema_file in sorted(schemas_dir.glob("*.json")):
    with open(schema_file) as f:
        schema = json.load(f)
    try:
        Draft202012Validator.check_schema(schema)
        print(f"OK  {schema_file.name}")
    except Exception as e:
        print(f"FAIL {schema_file.name}: {e}")
