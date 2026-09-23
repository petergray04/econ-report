import copy
import hashlib
import json

import pytest

from econ.render import ROOT
from econ.validate import publish_issues, schema_errors, validate

REF_PATH = ROOT / "data" / "2026-09-23.json"
REF = json.loads(REF_PATH.read_text())

# data/2026-09-23.json is the fully researched, verified first edition. Its numbers must never change.
REF_SHA256 = "5c3558a3ad1ae1eb074dea22873dc491dc691905f5041335d077bae9bfd5f0c2"


def test_reference_edition_is_unchanged():
    assert hashlib.sha256(REF_PATH.read_bytes()).hexdigest() == REF_SHA256, \
        "data/2026-09-23.json changed — the verified numbers must not be edited"


def test_reference_edition_is_publishable():
    errors, _ = validate(REF, REF_PATH)
    assert errors == []


def first_row(d):
    return d["sections"][0]["rows"][0]


@pytest.mark.parametrize("mutate, expect", [
    (lambda d: first_row(d).update(needs_review=True, review=["consensus"]), "needs_review"),
    (lambda d: first_row(d).update(url=""), "schema"),
    (lambda d: first_row(d).pop("src"), "schema"),
    (lambda d: first_row(d).update(fmt="pct3"), "schema"),
    (lambda d: first_row(d).update(better="up"), "schema"),
    (lambda d: first_row(d)["p2"].update(act=None), "actual is empty"),
    (lambda d: first_row(d)["p2"].update(cons="207"), "schema"),
    (lambda d: d.update(status="draft"), "draft"),
    (lambda d: d["ms"].update(note="Per public press."), "schema"),
    (lambda d: d["kpis"].pop(), "schema"),
    (lambda d: d["sections"].pop(), "schema"),
    (lambda d: d.update(extra_key=1), "schema"),
    (lambda d: first_row(d).update(note="No public consensus"), "no public consensus"),
])
def test_publish_rules_catch_problems(mutate, expect):
    d = copy.deepcopy(REF)
    mutate(d)
    errors, _ = validate(d, REF_PATH)
    assert errors and any(expect in e for e in errors), errors


def test_draft_mode_allows_review_flags_but_lists_them():
    d = copy.deepcopy(REF)
    d["status"] = "draft"
    first_row(d).update(needs_review=True, review=["consensus (Bloomberg via First Trust)"])
    first_row(d)["p2"]["cons"] = None
    errors, todos = validate(d, REF_PATH, mode="draft")
    assert errors == []
    assert any("needs_review" in t for t in todos)


def test_null_consensus_is_valid():
    d = copy.deepcopy(REF)
    first_row(d)["p1"]["cons"] = None
    assert schema_errors(d) == [] and publish_issues(d) == []
