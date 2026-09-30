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
        self.skip = 0          # inside an (i) button or its popover: not part of the cell's value

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip or (tag == "button" and "info" in (a.get("class") or "")) or "popover" in a:
            if tag not in ("br", "img", "input"):
                self.skip += 1
            return
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
        if self.skip:
            self.skip -= 1
            return
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
        if self.cell is not None and not self.skip:
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


def test_consensus_ranges_format_and_color():
    from econ.formatting import fmt, verdict
    assert fmt({"lo": 3.2, "hi": 3.5}, "pct") == "3.2–3.5%"
    assert fmt({"lo": 1320, "hi": 1345}, "k") == "1,320–1,345"
    assert fmt({"lo": -0.1, "hi": 0.2}, "pct") == "−0.1–0.2%"
    assert fmt({"lo": -39, "hi": -7}, "k") == "−39 to −7"
    lower = {"better": "lower"}
    rng = {"lo": 3.2, "hi": 3.5}
    assert [verdict(lower, {"cons": rng, "act": a}) for a in (3.1, 3.2, 3.4, 3.5, 3.6)] == \
        ["beat", "", "", "", "miss"]
    assert verdict({"better": "higher"}, {"cons": rng, "act": 3.6}) == "beat"


def test_range_renders_in_table():
    import copy
    d = copy.deepcopy(REF)
    row = d["sections"][0]["rows"][3]          # Nonfarm Payrolls
    row["p2"]["cons"] = {"lo": 40, "hi": 90}
    html = render("edition.html", d=d, archive=archive_entries([d]), latest=d, root="", is_latest=True)
    cells = {c[0]: c for c, _ in parse(html)}
    assert cells["Nonfarm Payrolls (000s)"][5] == "40–90"
    assert 'class="num rng">40–90<' in html


def test_every_indicator_has_an_explanation_and_numbers_survive_the_buttons():
    from econ.render import glossary
    from econ.series import row_keys
    gloss = glossary()
    keys = [k for sec in REF["sections"] for k, _ in row_keys(sec)]
    assert [k for k in keys if k not in gloss] == []
    for k in ("block:gdp", "block:targets", "block:markets", "block:sentiment"):
        assert k in gloss
    html = render("edition.html", d=REF, archive=archive_entries([REF]), latest=REF, root="", is_latest=True, gloss=gloss)
    assert html.count('class="info"') == len(keys) + 3          # every row + GDP/targets/markets cards
    got = parse(html)
    assert [c for c, _ in got] == [e for _, e in expected_rows(REF)]
    pdf = render("report_pdf.html", d=REF)
    assert 'class="info"' not in pdf and "popover" not in pdf    # buttons are website-only


SENTI = {"aaii": {"week": "9/24", "bull": 32.5, "neutral": 28.0, "bear": 39.5,
                  "avg_bull": 37.5, "avg_neutral": 31.5, "avg_bear": 31.0,
                  "url": "https://www.aaii.com/sentimentsurvey"},
         "fear_greed": {"value": 38, "label": "Fear", "asof": "Sep 29",
                        "url": "https://www.cnn.com/markets/fear-and-greed"}}


def test_sentiment_block_renders_and_hides_when_blank():
    import copy
    from econ.formatting import mood_of, spread
    d = copy.deepcopy(REF)
    d["sentiment"] = SENTI
    html = render("edition.html", d=d, archive=archive_entries([d]), latest=d, root="", is_latest=True)
    assert "Market Sentiment" in html and "Bearish" in html and "−7.0 pts" in html and ">38<" in html
    assert mood_of(SENTI["aaii"]) == {"label": "Bearish", "cls": "miss"} and spread(37.5, 31.0) == "+6.5 pts"
    d["sentiment"] = {"aaii": dict(SENTI["aaii"], bull=None, neutral=None, bear=None),
                      "fear_greed": dict(SENTI["fear_greed"], value=None, label=None)}
    assert "Market Sentiment" not in render("edition.html", d=d, archive=[], latest=d, root="", is_latest=True)
    assert "Market Sentiment" not in render("report_pdf.html", d=REF)   # older editions have no block
