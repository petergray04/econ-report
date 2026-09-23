#!/usr/bin/env python3
"""Monday automation: draft next week's edition, or finalize a reviewed draft.

  python3 draft_edition.py                        # draft data/<next Monday>.json from the latest edition
  python3 draft_edition.py --date 2026-09-28      # choose the edition date
  python3 draft_edition.py --pr-body out/pr.md    # also write the pull-request checklist
  python3 draft_edition.py --finalize data/2026-09-28.json
        # after review: refuses while any needs_review remains; otherwise removes the draft markers

See econ/draft.py for exactly what is and isn't filled in automatically.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

from econ.draft import finalize, make_draft, next_monday, pr_body
from econ.fred import Fred
from econ.site import DATA_DIR, load_editions


def dump(d):
    return json.dumps(d, indent=1, ensure_ascii=True) + "\n"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="edition date YYYY-MM-DD (default: next Monday, today if Monday)")
    ap.add_argument("--pr-body", help="write the PR checklist markdown here")
    ap.add_argument("--finalize", metavar="FILE")
    ap.add_argument("--force", action="store_true", help="overwrite an existing data file")
    a = ap.parse_args(argv)

    if a.finalize:
        path = pathlib.Path(a.finalize)
        d = json.loads(path.read_text())
        blockers = finalize(d)
        if blockers:
            print(f"Not ready — {len(blockers)} item(s) left:")
            print("\n".join(f"  - {b}" for b in blockers))
            return 1
        path.write_text(dump(d))
        print(f"{path} finalized. Next: make build (checks the PDF is 2 pages), then push/merge.")
        return 0

    date = dt.date.fromisoformat(a.date) if a.date else next_monday()
    out = DATA_DIR / f"{date.isoformat()}.json"
    if out.exists() and not a.force:
        print(f"{out} already exists; nothing to do (use --force to regenerate).")
        return 0
    published = [e for e in load_editions() if e["edition"] < date.isoformat()]
    if not published:
        print("No earlier published edition to start from.")
        return 1
    prev = published[0]
    fred = Fred()
    if not fred.key:
        print("warning: FRED_API_KEY not set — using weekly ALFRED sampling (slower, release day approximate)")
    d, todo, log = make_draft(prev, date, fred)
    out.write_text(dump(d))
    print("\n".join(log))
    n = sum(1 for s in d["sections"] for r in s["rows"] if r.get("needs_review"))
    print(f"\nWrote {out} (draft) from {prev['edition']}: {n} row(s) need review, {len(todo)} other to-dos.")
    if a.pr_body:
        p = pathlib.Path(a.pr_body)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(pr_body(d, f"data/{prev['edition']}.json", log))
        print(f"PR checklist: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
