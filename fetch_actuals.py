#!/usr/bin/env python3
"""Pull FIRST-PRINT actuals from FRED/ALFRED for every FRED-covered row.

  python3 fetch_actuals.py                         # latest two releases per row -> out/actuals_<today>.csv
  python3 fetch_actuals.py CPI Payrolls            # only rows whose key contains these words
  python3 fetch_actuals.py --check data/2026-09-23.json
        # regression test: recompute every FRED-covered row of that edition for ITS periods
        # and compare with the published numbers (exit 1 on any mismatch)

Set FRED_API_KEY (env or a git-ignored .env file) for exact release-day vintages; without a key the
script falls back to weekly ALFRED sampling. Responses are cached in .cache/fred/.

Method: see econ/series.py — first print, by-date comparisons, NSA index for CPI/PPI YoY.
Rows not on FRED (ISM, NFIB, NAHB, LEI, UMich, NAR, ...) and ALL consensus figures are entered by hand.
"""
import concurrent.futures as cf
import csv
import datetime as dt
import json
import pathlib
import sys
import time

from econ.fred import Fred, FredError
from econ.series import (DECIMALS, EXTRAS, MANUAL, MARKETS, ROWS, Fetcher, period_to_obs,
                         round_half_up, row_keys)

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"


def run_parallel(jobs):
    """jobs: {name: callable}. Runs 3 at a time (the Fred client also throttles globally)."""
    results = {}
    with cf.ThreadPoolExecutor(3) as ex:
        futs = {ex.submit(fn): name for name, fn in jobs.items()}
        for f in cf.as_completed(futs):
            try:
                results[futs[f]] = f.result()
            except FredError as e:
                results[futs[f]] = e
    return results


def fmt_num(v, places=2):
    return "" if v is None else f"{v:.{places}f}"


def latest(fetcher, filters):
    specs = {k: s for k, s in {**ROWS, **EXTRAS}.items() if not filters or any(f in k.lower() for f in filters)}
    res = run_parallel({k: (lambda s=s: fetcher.prints(s, fetcher.latest_obs(s))) for k, s in specs.items()})
    rows = []
    for k in specs:
        r = res[k]
        if isinstance(r, Exception):
            rows.append([k, specs[k].sid, "ERROR", "", str(r), "", ""])
            continue
        for p in r:
            rows.append([k, specs[k].sid, p.obs, p.release or "", fmt_num(p.first), fmt_num(p.current), specs[k].mode])
    if not filters:
        start = "2025-12-01"
        for name, sid in MARKETS.items():
            cur = fetcher.current_series(sid, start)
            k = sorted(cur)
            ye = [d for d in k if d <= "2025-12-31"][-1]
            rows.append([name, sid, k[-1], "", fmt_num(cur[k[-1]]), f"YTD {100 * (cur[k[-1]] / cur[ye] - 1):.1f}%", "current"])
    OUT.mkdir(exist_ok=True)
    path = OUT / f"actuals_{dt.date.today().isoformat()}.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "fred_id", "observation", "first_published", "first_print", "current_value", "mode"])
        w.writerows(rows)
    print(f"{'row':52} {'obs':10} {'1st print':>10} {'current':>10}  first published")
    for r in rows:
        print(f"{r[0][:52]:52} {r[2]:10} {r[4]:>10} {r[5]:>10}  {r[3]}")
    print(f"\nWrote {path.relative_to(ROOT)}")
    print("Manual rows (not on FRED):", ", ".join(MANUAL))
    return 0


def check(fetcher, data_path):
    """Recompute every FRED-covered row of an edition for its own periods and compare."""
    d = json.loads(pathlib.Path(data_path).read_text())
    targets = []
    for sec in d["sections"]:
        for key, r in row_keys(sec):
            if key in ROWS:
                obs = [period_to_obs(r[p]["period"], d["edition"]) for p in ("p1", "p2")]
                targets.append((key, r, obs))
    res = run_parallel({key: (lambda s=ROWS[key], o=obs: fetcher.prints(s, o)) for key, r, obs in targets})
    bad = 0
    print(f"{'row':52} {'period':8} {'published':>10} {'fetched':>10} {'current':>9}  first published")
    for key, r, obs in targets:
        places = DECIMALS[r["fmt"]]
        prints = res[key]
        for i, p in enumerate(("p1", "p2")):
            want = r[p]["act"]
            if isinstance(prints, Exception):
                got, cur, rel = None, None, f"ERROR {prints}"
            else:
                pr = prints[i]
                got, cur, rel = round_half_up(pr.first, places), round_half_up(pr.current, places), pr.release or pr.freq
            ok = got is not None and abs(got - want) < 1e-9
            bad += not ok
            mark = "  " if ok else "✗ "
            print(f"{mark}{key[:50]:50} {r[p]['period']:8} {want:>10} {'' if got is None else got:>10} "
                  f"{'' if cur is None else cur:>9}  {rel}")
    total = 2 * len(targets)
    print(f"\n{total - bad}/{total} FRED-covered values match {data_path} ({len(targets)} rows; "
          f"{len(MANUAL)} rows are manual).")
    return 1 if bad else 0


def main(argv):
    t0 = time.time()
    fred = Fred(verbose="-v" in argv)
    fetcher = Fetcher(fred)
    print(f"FRED mode: {'API key (exact ALFRED vintages)' if fred.key else 'no key (weekly ALFRED sampling)'}\n")
    args = [a for a in argv if not a.startswith("-")]
    if "--check" in argv:
        rc = check(fetcher, args[0])
    else:
        rc = latest(fetcher, [a.lower() for a in args])
    s = fred.stats
    print(f"\n{s['requests']} HTTP requests, {s['cache_hits']} cache hits, {s['retries']} retries, "
          f"{time.time() - t0:.1f}s")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
