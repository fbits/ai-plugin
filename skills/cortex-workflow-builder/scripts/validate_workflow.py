#!/usr/bin/env python3
"""Validate a Cortex v2 workflow definition.

Checks both gates the engine applies:
  Gate 1 (JSON Schema): only if the `jsonschema` package is installed.
  Gate 2 (semantic + runtime): always — these are the rules the JSON Schema
          does NOT catch and that most often break a workflow at runtime.

Usage:
    python validate_workflow.py path/to/workflow.json

Exit code 0 = valid, 1 = errors found. Warnings never fail the run.
"""
import json
import sys
from pathlib import Path

STEP_TYPES = {"constant", "passthrough", "branch", "http", "llm", "function", "result"}

# config keys the RUNTIME PARSER requires (stricter than the JSON Schema in places).
REQUIRED_CONFIG = {
    "llm": ["userPrompt", "model"],   # model is required by the parser, not the schema
    "result": ["userPrompt", "model"],  # terminal LLM step; parser requires both
    "http": ["url"],
    "branch": ["on", "cases"],
    "constant": ["value"],
    "passthrough": ["transform"],
    "function": ["name", "version"],  # parser reads name+version (schema names it `function`)
}


def validate(doc):
    errors, warnings = [], []

    for field in ("name", "version", "start", "steps"):
        if field not in doc:
            errors.append(f"missing required top-level field: '{field}'")
    steps = doc.get("steps") or []
    if not isinstance(steps, list) or not steps:
        errors.append("'steps' must be a non-empty array")
        return errors, warnings

    ids = [s.get("id") for s in steps]
    seen = set()
    for sid in ids:
        if not sid:
            errors.append("a step is missing 'id'")
        elif sid in seen:
            errors.append(f"duplicate step id: '{sid}'")
        else:
            seen.add(sid)
    id_set = set(i for i in ids if i)

    finals = [s.get("id") for s in steps if s.get("output") == "final"]
    bad_output = [s.get("id") for s in steps if s.get("output") not in (None, "final")]
    for sid in bad_output:
        errors.append(f"step '{sid}': 'output' may only be the literal \"final\"")
    if len(finals) == 0:
        errors.append('no step has "output": "final" (exactly one is required)')
    elif len(finals) > 1:
        errors.append(f'multiple final steps: {finals} (exactly one allowed)')

    start = doc.get("start")
    if start and start not in id_set:
        errors.append(f"'start' references unknown step id: '{start}'")

    for s in steps:
        sid, stype, cfg = s.get("id"), s.get("type"), s.get("config") or {}
        if stype not in STEP_TYPES:
            errors.append(f"step '{sid}': unknown type '{stype}'")
            continue
        for key in REQUIRED_CONFIG.get(stype, []):
            if key not in cfg:
                errors.append(f"step '{sid}' ({stype}): config missing required '{key}'")
        if stype in ("llm", "result") and "provider" in cfg:
            warnings.append(f"step '{sid}': 'provider' is ignored by the engine; only 'model' is read")
        if stype == "passthrough" and "value" in cfg and not isinstance(cfg["value"], str):
            errors.append(f"step '{sid}': passthrough 'value' must be a string template (use 'constant' for non-strings)")

    # branch case targets and matching edges
    edges = doc.get("edges") or []
    for s in steps:
        if s.get("type") != "branch":
            continue
        cfg = s.get("config") or {}
        targets = list((cfg.get("cases") or {}).values())
        if cfg.get("default"):
            targets.append(cfg["default"])
        for tgt in targets:
            if tgt not in id_set:
                errors.append(f"branch '{s.get('id')}': case target '{tgt}' is not a step id")
            has_edge = any(e.get("from") == s.get("id") and e.get("to") == tgt
                           and str(e.get("condition", "")).startswith("branch:") for e in edges)
            if not has_edge:
                warnings.append(f"branch '{s.get('id')}': no 'branch:' edge carries control to '{tgt}'")

    for e in edges:
        frm, to, cond = e.get("from"), e.get("to"), e.get("condition")
        if frm not in id_set:
            errors.append(f"edge from unknown step id: '{frm}'")
        if to not in id_set:
            errors.append(f"edge to unknown step id: '{to}'")
        if cond not in (None, "success", "error") and not str(cond).startswith("branch:"):
            errors.append(f"edge {frm}->{to}: invalid condition '{cond}' "
                          "(use success | error | branch:<case>)")

    return errors, warnings


def try_schema_validation(doc):
    try:
        import jsonschema
    except ImportError:
        return None
    schema_path = Path(__file__).parent.parent / "assets" / "workflow-meta-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(doc)]


def main():
    if len(sys.argv) != 2:
        print("usage: python validate_workflow.py path/to/workflow.json")
        sys.exit(2)
    doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    schema_errors = try_schema_validation(doc)
    if schema_errors is None:
        print("[schema] skipped (install 'jsonschema' to enable Gate 1)")
    elif schema_errors:
        print("[schema] FAILED:")
        for e in schema_errors:
            print(f"  - {e}")
    else:
        print("[schema] OK")

    errors, warnings = validate(doc)
    for w in warnings:
        print(f"[warn] {w}")
    if errors:
        print("[semantic] FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("[semantic] OK")
    if schema_errors:
        sys.exit(1)
    print(f"\nVALID: '{doc.get('name')}' v{doc.get('version')}, {len(doc.get('steps', []))} steps")


if __name__ == "__main__":
    main()
