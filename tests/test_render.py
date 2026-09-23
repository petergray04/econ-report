"""The rendered page and PDF source must show exactly the numbers in the data file."""
import json
from html.parser import HTMLParser

import pytest

from econ.formatting import fmt, verdict
from econ.render import ROOT, render
from econ.site import archive_entries

REF = json.loads((ROOT / "data" / "2026-09-23.json").read_text())


class Rows(HTMLParser):
    """Collect the cell text of every body row in the indicator tables (section.block)."""

    def __init__(self):
        super().__init__()
        self.depth_block, self.in_tbody, self.row, self.cell, self.rows, self.classes = 0, False, None, None, [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and "block" in (a.get("class") or ""):
            self.depth_block += 1
        elif self.depth_block and tag == "tbody":
            self.in_tbody = True
        elif self.in_tbody and tag == "tr":
            self.row, self.classes = [], []
        elif self.row is not None and tag in ("td", "th"):
            self.cell = ""
            self.classes.append(a.get("class") or "")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append((self.row, self.classes))
            self.row = None
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "section" and self.depth_block:
            self.depth_block -= 1

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def expected_rows(d):
    for sec in d["sections"]:
        for r in sec["rows"]:
            cells = [r["label"]]
            for p in (r["p1"], r["p2"]):
                cells += [p["period"], fmt(p["cons"], r["fmt"]), fmt(p["act"], r["fmt"])]
            yield r, cells + [r["note"], r["src"]]


def parse(html):
    p = Rows()
    p.feed(html)
    return p.rows


@pytest.mark.parametrize("template, ctx", [
    ("report_pdf.html", {}),
    ("edition.html", {"root": "", "is_latest": True}),
])
def test_every_indicator_cell_matches_data(template, ctx):
    html = render(template, d=REF, archive=archive_entries([REF]), latest=REF, **ctx)
    got = parse(html)
    want = list(expected_rows(REF))
    assert len(got) == len(want) == 45
    for (cells, classes), (r, exp) in zip(got, want):
        assert cells == exp, r["label"]
        # beat/miss coloring on the two Actual cells (indexes 3 and 6)
        for idx, p in ((3, r["p1"]), (6, r["p2"])):
            assert classes[idx].split()[2:] == ([verdict(r, p)] if verdict(r, p) else []), r["label"]


def test_regression_headline_numbers_render():
    html = render("edition.html", d=REF, archive=archive_entries([REF]), latest=REF, root="", is_latest=True)
    rows = {c[0]: c for c, _ in parse(html)}
    assert rows["Nonfarm Payrolls (000s)"][6] == "162"
    assert rows["CPI (YoY)"][6] == "3.4%"
    assert rows["Housing Starts (000s)"][6] == "1,275"


def test_null_consensus_renders_as_dash():
    assert fmt(None, "pct") == "—"


def test_no_claude_artifact_leftovers():
    html = render("edition.html", d=REF, archive=archive_entries([REF]), latest=REF, root="", is_latest=True)
    assert "window.claude" not in html and "/_blob/" not in html
    assert 'href="pdfs/Economic_Report_2026-09-23.pdf" download' in html
