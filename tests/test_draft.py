"""Draft logic: roll the verified edition back one release and check the draft rebuilds it."""
import copy
import datetime as dt
import json
import os

import pytest

from econ.draft import finalize, make_draft, pr_body
from econ.render import ROOT
from econ.series import MANUAL, ROWS, row_keys
from econ.validate import validate

REF = json.loads((ROOT / "data" / "2026-09-23.json").read_text())


def rolled_back(d):
    """Previous-week view of the edition: every FRED row's latest release removed."""
    prev = copy.deepcopy(d)
    prev["edition"] = "2026-09-16"
    for sec in prev["sections"]:
        for key, r in row_keys(sec):
            if key in ROWS and ROWS[key].mode == "first":
                r["p2"] = r["p1"]
                r["p1"] = {"period": "?", "cons": None, "act": None}
    return prev


def test_finalize_refuses_while_flags_remain():
    d = copy.deepcopy(REF)
    d["status"] = "draft"
    d["sections"][0]["rows"][0].update(needs_review=True, review=["consensus"])
    assert finalize(d)
    assert d["status"] == "draft"


def test_finalize_clears_markers_when_done():
    d = copy.deepcopy(REF)
    d["status"] = "draft"
    d["draft_meta"] = {"todo": []}
    assert finalize(d) == []
    assert "status" not in d and "draft_meta" not in d


@pytest.mark.skipif(not os.environ.get("FRED_LIVE"), reason="live FRED check; set FRED_LIVE=1")
def test_draft_rebuilds_verified_edition_from_previous_week():
    draft, todo, log = make_draft(rolled_back(REF), dt.date(2026, 9, 23))
    errors, todos = validate(draft, mode="draft")
    assert errors == []
    for sec_draft, sec_ref in zip(draft["sections"], REF["sections"]):
        for (key, r), (_, ref) in zip(row_keys(sec_draft), row_keys(sec_ref)):
            if key in MANUAL:
                assert r["needs_review"] and r["p2"] == ref["p2"]
            elif ROWS[key].mode == "first":
                assert r["p2"]["period"] == ref["p2"]["period"], key
                assert r["p2"]["act"] == ref["p2"]["act"], key          # first print, fetched
                assert r["p2"]["cons"] is None and r["needs_review"], key  # consensus never invented
                assert r["p1"] == ref["p1"], key                          # shifted, first print + consensus kept
    # FRED index closes for 9/22 are final, so those rows reproduce exactly. EFA/EEM (Yahoo) and
    # Treasury yields (FRED, 1-day lag) for 9/22 were published only after the edition was built,
    # so re-running today legitimately picks up a newer close for them; check only their shape.
    ref_rows = {row[0]: row for row in REF["markets"]["rows"]}
    for row in draft["markets"]["rows"]:
        if row[0] in ("S&P 500", "Dow Jones", "NASDAQ Comp."):
            assert row == ref_rows[row[0]], row[0]
        else:
            assert row[2] == ref_rows[row[0]][2] and isinstance(row[3], float), row[0]
    assert draft["data_through"].startswith("Market data as of Sep 22, 2026 close")
    assert "Rows needing review" in pr_body(draft, "data/2026-09-16.json", log)
