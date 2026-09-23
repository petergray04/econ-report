"""Draft next week's edition from last week's file + FRED.

What it does (and deliberately does NOT do):
  * FRED rows with a new release: shift latest -> prior, fill the new FIRST PRINT, set consensus
    to null and flag needs_review (consensus must be sourced by hand — never estimated).
    If the prior release was revised since, the review list says so (revision goes in Notes;
    the prior's Actual stays the first print).
  * Manual rows (ISM, NFIB, NAHB, LEI, UMich, NAR, Ex Auto & Gas): flagged "check for a new
    release", values left untouched.
  * Markets block + data_through: refreshed from FRED (indexes, Treasuries) and Yahoo (EFA/EEM).
  * KPIs, story, watch list, GDP/IMF/MS blocks: left as-is and listed as to-dos.
The draft carries "status": "draft", so build.py and the site skip it until it is finalized.
"""
import copy
import datetime as dt
import json
import urllib.request

from .fred import Fred
from .series import (DECIMALS, MANUAL, ROWS, Fetcher, period_label, period_style, period_to_obs,
                     round_half_up, row_keys)
from .validate import validate

YEAR_END = "2025-12-31"        # returns are measured from the end-2025 close
INDEXES = {"S&P 500": "SP500", "Dow Jones": "DJIA", "NASDAQ Comp.": "NASDAQCOM"}
ETFS = {"EAFE (EFA)": "EFA", "Emerging Mkts (EEM)": "EEM"}
RATES = {"10-Yr Treasury": "DGS10", "30-Yr Treasury": "DGS30"}


def next_monday(today=None):
    today = today or dt.date.today()
    return today + dt.timedelta(days=(7 - today.weekday()) % 7)


def edition_label(d):
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def short_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def flag(row, *items):
    row["needs_review"] = True
    row.setdefault("review", [])
    row["review"] += [i for i in items if i not in row["review"]]


# ---------- indicator rows ----------
def update_rows(d, fetcher, log):
    edition = d["edition"]
    for sec in d["sections"]:
        for key, r in row_keys(sec):
            if key in MANUAL:
                flag(r, f"check for a new release since last edition ({MANUAL[key]}); if new, shift latest→prior, "
                        "enter the actual and consensus")
                continue
            spec = ROWS.get(key)
            if spec is None:
                flag(r, "row is not mapped to FRED or the manual list — check by hand")
                continue
            style = period_style(r["p2"]["period"])
            old_p2_obs = period_to_obs(r["p2"]["period"], edition)
            latest = fetcher.latest_obs(spec, 2)
            new = [o for o in latest if old_p2_obs is None or o > old_p2_obs]
            if not new:
                continue
            prints = {p.obs: p for p in fetcher.prints(spec, latest)}
            places = DECIMALS[r["fmt"]]
            if len(new) == 1:
                # normal case: one new release -> old latest becomes prior (keeps its first print + consensus)
                prior = r["p2"]
                pr_old = prints.get(old_p2_obs) or (fetcher.prints(spec, [old_p2_obs])[0] if old_p2_obs else None)
                if pr_old and pr_old.current is not None and prior["act"] is not None:
                    cur = round_half_up(pr_old.current, places)
                    if abs(cur - prior["act"]) > 1e-9:
                        flag(r, f"{prior['period']} revised from {prior['act']} to {cur} — mention in Notes "
                                "(Actual stays the first print)")
            else:
                # two or more releases since last edition: both slots are new
                p = prints[new[-2]]
                prior = {"period": period_label(p.obs, p.freq, style), "cons": None,
                         "act": round_half_up(p.first, places)}
                flag(r, f"prior period {prior['period']} is also new: add its consensus")
            p = prints[new[-1]]
            first = round_half_up(p.first, places)
            r["p1"] = prior
            r["p2"] = {"period": period_label(p.obs, p.freq, style), "cons": None, "act": first}
            flag(r, f"consensus for {r['p2']['period']} (Bloomberg via First Trust Data Watch → DJ/LSEG/FactSet "
                    "named in Notes → leave null)", "update Notes for the new release")
            if first is None:
                flag(r, f"first print for {r['p2']['period']} not available from ALFRED — enter from the agency release")
            log.append(f"{key}: new {r['p2']['period']} = {first} (first published {p.release or 'n/a'})")


# ---------- markets ----------
def yahoo_closes(symbol, start, before):
    """Daily closes {date: close} for completed sessions (date < before) from Yahoo's chart API."""
    p1 = int(dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.fromisoformat(before).replace(tzinfo=dt.timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        j = json.loads(resp.read().decode())
    res = j["chart"]["result"][0]
    off = res["meta"].get("gmtoffset", 0)
    out = {}
    for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        day = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date().isoformat()
        if c is not None and day < before:
            out[day] = c
    return out


def update_markets(d, fetcher, edition_date, todo, log):
    """Refresh index levels, ETF prices and yields from completed sessions only (before today and
    before the edition date), so a mid-session run never picks up a partial day."""
    today = min(edition_date, dt.date.today())
    m = d["markets"]
    rows = {r[0]: r for r in m["rows"]}
    start = "2025-12-15"
    last_idx = None
    for name, sid in INDEXES.items():
        c = fetcher.current_series(sid, start)
        k = [x for x in sorted(c) if x < today.isoformat()]
        ye = [x for x in k if x <= YEAR_END][-1]
        rows[name][1] = f"{c[k[-1]]:,.2f}"
        rows[name][3] = round_half_up(100 * (c[k[-1]] / c[ye] - 1), 1)
        last_idx = k[-1]
    etf_date = None
    try:
        for name, sym in ETFS.items():
            c = yahoo_closes(sym, start, today.isoformat())
            k = sorted(c)
            ye = [x for x in k if x <= YEAR_END][-1]
            rows[name][1] = f"${c[k[-1]]:,.2f}"
            rows[name][3] = round_half_up(100 * (c[k[-1]] / c[ye] - 1), 1)
            etf_date = k[-1]
    except Exception as e:  # Yahoo is unofficial; never block the draft on it
        todo.append(f"EFA/EEM not refreshed (Yahoo chart API: {e}) — update by hand")
    rate_date = None
    for r in m["rates"]:
        c = fetcher.current_series(RATES[r[0]], start)
        k = [x for x in sorted(c) if x < today.isoformat()]
        r[1] = c[[x for x in k if x <= YEAR_END][-1]]
        r[2] = c[k[-1]]
        rate_date = k[-1]
    m["note"] = f"Price returns. Treasury yields: end-2025 vs {short_date(rate_date)} (constant maturity)."
    if etf_date is None:
        etf = " (EFA/EEM: NOT REFRESHED)"
    else:
        etf = f" (EFA/EEM: {short_date(etf_date)[:-6]})" if etf_date != last_idx else ""
    d["data_through"] = f"Market data as of {short_date(last_idx)} close{etf}"
    log.append(f"markets refreshed through {last_idx} (ETFs {etf_date or 'not refreshed'}, yields {rate_date})")


# ---------- whole edition ----------
def make_draft(prev, date, fred=None):
    """Return (draft_dict, todo_list, log_list)."""
    fetcher = Fetcher(fred or Fred())
    d = copy.deepcopy(prev)
    d["edition"] = date.isoformat()
    d["edition_label"] = edition_label(date)
    d["status"] = "draft"
    log, todo = [], []
    update_rows(d, fetcher, log)
    update_markets(d, fetcher, date, todo, log)
    todo += [
        "KPI strip (6 tiles): update values, details and up/dn tone for this week's headline prints",
        "Story: rewrite 'The week in one paragraph'",
        "On deck: replace with confirmed release dates from agency calendars only",
        "GDP block: check for a new GDP estimate, GDPNow, ULC, ECI",
        "Forecasts & Targets: check IMF WEO / Morgan Stanley (public press only; keep the caveat)",
        "Markets: spot-check the refreshed levels and the S&P/10-yr KPI tiles",
    ]
    d["draft_meta"] = {"based_on": prev["edition"], "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "todo": todo}
    return d, todo, log


def review_items(d):
    for sec in d["sections"]:
        for key, r in row_keys(sec):
            if r.get("needs_review"):
                yield sec["title"], key, r


def pr_body(d, prev_path, log):
    lines = [f"Automated draft of the **{d['edition_label']}** edition, based on `{prev_path}`.", "",
             "The draft is marked `\"status\": \"draft\"`, so it is **not published** until you finish it. "
             "The PR check stays red until every item below is resolved.", "",
             "### How to finish", "",
             "1. Work through the rows below in `data/" + d["edition"] + ".json`. When a row is done, delete its "
             "`needs_review` and `review` keys.",
             "2. Consensus policy: Bloomberg median via First Trust Data Watch → Dow Jones / LSEG / FactSet "
             "(name it in Notes) → otherwise leave `null` (renders “—”). **Never estimate.**",
             "3. Run `python draft_edition.py --finalize data/" + d["edition"] + ".json`, then `make build` "
             "and check the PDF is still 2 pages.",
             "4. Push to this branch and merge. The merge deploys the site.", ""]
    groups = {}
    for title, key, r in review_items(d):
        groups.setdefault(title, []).append((key, r))
    n = sum(len(v) for v in groups.values())
    lines.append(f"### Rows needing review ({n})")
    for title, items in groups.items():
        lines += ["", f"**{title}**"]
        for key, r in items:
            lines.append(f"- [ ] **{key}** — latest `{r['p2']['period']}`: actual `{r['p2']['act']}`, "
                         f"consensus `{r['p2']['cons']}`")
            lines += [f"  - {x}" for x in r.get("review", [])]
    lines += ["", "### Other blocks", ""] + [f"- [ ] {t}" for t in d["draft_meta"]["todo"]]
    lines += ["", "<details><summary>Fetch log</summary>", "", "```"] + log + ["```", "</details>"]
    return "\n".join(lines)


def finalize(d):
    """Strip draft markers if (and only if) nothing is left to review. Returns list of blockers."""
    blockers = [f"{t} › {k}: {'; '.join(r.get('review') or ['flagged'])}" for t, k, r in review_items(d)]
    if blockers:
        return blockers
    d.pop("status", None)
    d.pop("draft_meta", None)
    errors, _ = validate(d)
    return errors
