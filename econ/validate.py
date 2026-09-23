"""Validate edition files: JSON Schema + publish rules the schema can't express.

Two modes:
  publish (default) — what CI enforces before deploying: no drafts, no needs_review, every
                      actual filled, every row sourced.
  draft             — schema only, plus the same checks reported as a to-do list.
"""
import datetime as dt
import json
import pathlib

from jsonschema import Draft202012Validator

from .render import ROOT

SCHEMA = json.loads((ROOT / "schema" / "edition.schema.json").read_text())
_validator = Draft202012Validator(SCHEMA)


def iter_rows(d):
    for sec in d["sections"]:
        for r in sec["rows"]:
            yield sec["title"], r


def schema_errors(d):
    return [f"schema: /{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in sorted(_validator.iter_errors(d), key=lambda e: list(map(str, e.absolute_path)))]


def publish_issues(d, filename=None):
    """Rules for a publishable edition. Returns human-readable issue strings."""
    out = []
    if d.get("status") == "draft":
        out.append('edition is still marked "status": "draft"')
    if "draft_meta" in d:
        out.append('remove "draft_meta" before publishing')
    if filename and pathlib.Path(filename).stem != d.get("edition"):
        out.append(f'file name {pathlib.Path(filename).name} does not match edition {d.get("edition")}')
    try:
        dt.date.fromisoformat(d["edition"])
    except (KeyError, ValueError):
        out.append("edition is not a valid date")
    for title, r in iter_rows(d):
        where = f'{title} › {r.get("label")}'
        if r.get("needs_review"):
            todo = "; ".join(r.get("review") or []) or "flagged"
            out.append(f"{where}: needs_review ({todo})")
        elif r.get("review"):
            out.append(f'{where}: remove leftover "review" list')
        if not r.get("src") or not r.get("url"):
            out.append(f"{where}: missing src/url")
        for key in ("p1", "p2"):
            p = r.get(key) or {}
            if p.get("act") is None:
                out.append(f"{where}: {key} actual is empty")
        if (r.get("p1") or {}).get("period") == (r.get("p2") or {}).get("period"):
            out.append(f"{where}: prior and latest period are the same ({r['p2']['period']})")
        note = (r.get("note") or "").lower()
        if "no public consensus" in note and any((r.get(k) or {}).get("cons") is not None for k in ("p1", "p2")):
            out.append(f'{where}: note says "no public consensus" but a consensus value is filled in')
    return out


def validate(d, filename=None, mode="publish"):
    errs = schema_errors(d)
    issues = publish_issues(d, filename)
    if mode == "publish":
        return errs + issues, []
    return errs, issues


def validate_files(paths, mode="publish"):
    """Returns (ok, report_lines)."""
    ok, lines = True, []
    for p in paths:
        p = pathlib.Path(p)
        try:
            d = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            ok = False
            lines.append(f"✗ {p}: invalid JSON: {e}")
            continue
        file_mode = mode if mode != "auto" else ("draft" if d.get("status") == "draft" else "publish")
        errors, todos = validate(d, p, file_mode)
        if errors:
            ok = False
            lines.append(f"✗ {p} ({file_mode}): {len(errors)} problem(s)")
            lines += [f"    - {e}" for e in errors]
        else:
            lines.append(f"✓ {p} ({file_mode})" + (f" — {len(todos)} item(s) to review before publishing" if todos else ""))
            lines += [f"    · {t}" for t in todos]
    return ok, lines
