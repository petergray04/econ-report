#!/usr/bin/env python3
"""Monday step 1 — pull the two most recent FIRST-PRINT actuals for every FRED-covered row.

  python3 fetch_actuals.py            -> writes out/actuals_YYYY-MM-DD.csv and prints a checklist

Method
- Values come from ALFRED vintages (what the series showed on release day), so they match
  what was reported, not today's revised number. Revised current values are shown alongside.
- YoY is computed BY DATE (same month a year earlier), never "12 rows back": FRED has a
  missing Oct-2025 observation (government shutdown) that breaks row-offset math.
- Series not on FRED (ISM, NFIB, NAHB, LEI, UMich prelim, MBA, pending home sales) and ALL
  consensus figures are entered by hand from the sources listed in RUNBOOK.md.
- No API key needed. Network access to fred.stlouisfed.org and alfred.stlouisfed.org required.
"""
import csv, io, urllib.request, urllib.error, datetime as dt, concurrent.futures as cf, pathlib, json

TODAY = dt.date.today()
OUT = pathlib.Path(__file__).parent / "out"

# row label -> (FRED id, transform, scale)   transform: lvl | diff | mom | yoy
SERIES = {
    "Initial Jobless Claims (000s)": ("ICSA", "lvl", 0.001),
    "Continuing Claims (000s)": ("CCSA", "lvl", 0.001),
    "ADP Private Employment (000s)": ("ADPMNUSNERSA", "diff", 0.001),
    "Nonfarm Payrolls (000s)": ("PAYEMS", "diff", 1),
    "Private Payrolls": ("USPRIV", "diff", 1),
    "Manufacturing Payrolls": ("MANEMP", "diff", 1),
    "Unemployment Rate": ("UNRATE", "lvl", 1),
    "U-6 (note)": ("U6RATE", "lvl", 1),
    "Participation (note)": ("CIVPART", "lvl", 1),
    "JOLTS Job Openings (000s)": ("JTSJOL", "lvl", 1),
    "Consumer Credit ($B)": ("TOTALSL", "diff", 0.001),
    "Personal Income (MoM)": ("PI", "mom", 1),
    "Personal Spending (MoM)": ("PCE", "mom", 1),
    "Retail Sales (MoM)": ("RSAFS", "mom", 1),
    "Industrial Production (MoM)": ("INDPRO", "mom", 1),
    "Capacity Utilization": ("TCU", "lvl", 1),
    "Durable Goods Orders (MoM)": ("DGORDER", "mom", 1),
    "Durables ex-Transport (note)": ("ADXTNO", "mom", 1),
    "Factory Orders (MoM)": ("AMTMNO", "mom", 1),
    "Construction Spending (MoM)": ("TTLCONS", "mom", 1),
    "Housing Starts (000s)": ("HOUST", "lvl", 1),
    "Housing Starts % MoM": ("HOUST", "mom", 1),
    "Building Permits (000s)": ("PERMIT", "lvl", 1),
    "Building Permits % MoM": ("PERMIT", "mom", 1),
    "New Home Sales (000s)": ("HSN1F", "lvl", 1),
    "New Home Sales % MoM": ("HSN1F", "mom", 1),
    "Case-Shiller 20-City (YoY, NSA)": ("SPCS20RNSA", "yoy", 1),
    "Freddie Mac 30-Yr Mortgage": ("MORTGAGE30US", "lvl", 1),
    "CPI (MoM)": ("CPIAUCSL", "mom", 1),
    "CPI (YoY)": ("CPIAUCNS", "yoy", 1),
    "Core CPI (MoM)": ("CPILFESL", "mom", 1),
    "Core CPI (YoY)": ("CPILFENS", "yoy", 1),
    "PPI Final Demand (MoM)": ("PPIFIS", "mom", 1),
    "PPI Final Demand (YoY)": ("PPIFIS", "yoy", 1),
    "Core PPI (MoM)": ("PPIFES", "mom", 1),
    "Core PPI (YoY)": ("PPIFES", "yoy", 1),
    "Core PCE (YoY)": ("PCEPILFE", "yoy", 1),
    "Core PCE (QoQ SAAR)": ("DPCCRV1Q225SBEA", "lvl", 1),
    "Real GDP (QoQ SAAR)": ("A191RL1Q225SBEA", "lvl", 1),
    "Unit Labor Costs": ("PRS85006112", "lvl", 1),
    "GDPNow": ("GDPNOW", "lvl", 1),
    "10-Yr Treasury": ("DGS10", "lvl", 1),
    "30-Yr Treasury": ("DGS30", "lvl", 1),
    "Fed Funds Upper": ("DFEDTARU", "lvl", 1),
}
# Existing home sales (NAR) is licensed and not in ALFRED; FRED's current value is used as a check only.
CURRENT_ONLY = {"Existing Home Sales (mil.)": ("EXHOSLUSM495S", "lvl", 1e-6)}
MARKETS = {"S&P 500": "SP500", "Dow Jones": "DJIA", "NASDAQ Comp.": "NASDAQCOM"}

def get(url, tries=5):
    import time
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for t in range(tries):
        try:
            txt = urllib.request.urlopen(req, timeout=40).read().decode()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 or t == tries - 1:
                raise
            time.sleep(2 * (t + 1))   # FRED returns 503 when hit too fast; back off
    rows = list(csv.reader(io.StringIO(txt)))[1:]
    return {d: float(v) for d, v in rows if v not in ("", ".")}

def fred(sid, start="2024-06-01"):
    return get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}")

def alfred(sid, vdate, start="2024-06-01"):
    try:
        return get(f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}&vintage_date={vdate}&cosd={start}")
    except Exception:
        return None

def transform(snap, obs, kind, scale):
    k = sorted(snap)
    i = k.index(obs)
    if kind == "lvl":
        return snap[obs] * scale
    if kind == "diff":
        return (snap[obs] - snap[k[i - 1]]) * scale
    if kind == "mom":
        return (snap[obs] / snap[k[i - 1]] - 1) * 100
    if kind == "yoy":
        prev = f"{int(obs[:4]) - 1}{obs[4:]}"      # by DATE, not row offset
        return (snap[obs] / snap[prev] - 1) * 100 if prev in snap else None

def first_prints(sid, kind, scale, n=2):
    cur = fred(sid)
    obs = sorted(cur)[-n:]
    daily = sid in ("ICSA", "CCSA", "MORTGAGE30US", "DGS10", "DGS30", "DFEDTARU", "GDPNOW")
    if daily:  # weekly/daily data: report current values (revisions are small and next-week)
        return [(o, None, transform(cur, o, kind, scale), transform(cur, o, kind, scale)) for o in obs]
    vdates = [TODAY - dt.timedelta(days=d) for d in range(0, 98, 7)][::-1]
    snaps = {}
    with cf.ThreadPoolExecutor(4) as ex:
        for v, s in zip(vdates, ex.map(lambda v: alfred(sid, v.isoformat()), vdates)):
            if s:
                snaps[v] = s
    out = []
    for o in obs:
        first = next(((v, s) for v, s in sorted(snaps.items()) if o in s), (None, None))
        fp = transform(first[1], o, kind, scale) if first[1] else None
        out.append((o, first[0], fp, transform(cur, o, kind, scale)))
    return out

def main():
    import sys
    # optional filter: python3 fetch_actuals.py CPI Payrolls  -> only rows whose label contains those words
    keys = [a.lower() for a in sys.argv[1:]]
    if keys:
        for k in list(SERIES):
            if not any(x in k.lower() for x in keys):
                SERIES.pop(k)
        CURRENT_ONLY.clear(); MARKETS.clear()
    OUT.mkdir(exist_ok=True)
    rows = []
    with cf.ThreadPoolExecutor(3) as ex:
        futs = {ex.submit(first_prints, *spec): lbl for lbl, spec in SERIES.items()}
        for f, lbl in futs.items():
            try:
                for o, rel, fp, cur in f.result():
                    rows.append([lbl, SERIES[lbl][0], o, rel or "", "" if fp is None else round(fp, 2), "" if cur is None else round(cur, 2)])
            except Exception as e:
                rows.append([lbl, SERIES[lbl][0], "ERROR", "", str(e), ""])
    for lbl, (sid, kind, sc) in CURRENT_ONLY.items():
        cur = fred(sid)
        for o in sorted(cur)[-2:]:
            rows.append([lbl, sid, o, "", "", round(transform(cur, o, kind, sc), 2)])
        rows.append([lbl + " % MoM", sid, sorted(cur)[-1], "", "", round(transform(cur, sorted(cur)[-1], "mom", 1), 2)])
    for name, sid in MARKETS.items():
        cur = fred(sid, "2025-12-01")
        k = sorted(cur); ye = [d for d in k if d <= "2025-12-31"][-1]
        rows.append([name, sid, k[-1], "", round(cur[k[-1]], 2), f"YTD {100*(cur[k[-1]]/cur[ye]-1):.1f}%"])
    rows.sort(key=lambda r: list(SERIES).index(r[0]) if r[0] in SERIES else 999)
    path = OUT / f"actuals_{TODAY.isoformat()}.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "fred_id", "observation", "first_seen_vintage", "first_print", "current_value"])
        w.writerows(rows)
    print(f"Wrote {path}\n")
    print(f"{'row':38} {'obs':11} {'1st print':>10} {'current':>10}  first seen")
    for r in rows:
        print(f"{r[0][:38]:38} {r[2]:11} {str(r[4]):>10} {str(r[5]):>10}  {r[3]}")
    print("\nNext: update data/<date>.json (actuals from 'first_print'; revisions go in Notes),"
          " add consensus + non-FRED rows per RUNBOOK.md, then run build.py.")

if __name__ == "__main__":
    main()
