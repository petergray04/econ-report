#!/usr/bin/env python3
"""Weekly U.S. Economic Indicators — build the static site.

Usage:
  python3 build.py                              # every published edition in data/ -> site/ (pages + PDFs)
  python3 build.py data/2026-09-23.json         # all pages; (re)build the PDF for this edition only
  python3 build.py --no-pdf                     # pages only (reuses PDFs already in site/pdfs/)

One data file feeds both the PDF and the web page, so they can never disagree.
The archive is derived from data/*.json (files with "status": "draft" are skipped).
The build fails if any PDF is not exactly 2 Letter pages.
"""
import json
import pathlib
import sys

from econ.site import build_site, clean, load_editions


def main(argv):
    no_pdf = "--no-pdf" in argv
    files = [pathlib.Path(a) for a in argv if not a.startswith("--")]
    editions = load_editions()
    for f in files:
        d = json.loads(f.read_text())
        if d.get("status") == "draft":
            raise SystemExit(f"{f} is still a draft; finish review and remove \"status\": \"draft\" first.")
    wanted = {json.loads(f.read_text())["edition"] for f in files} if files else {d["edition"] for d in editions}
    clean()
    build_site(editions, pdf_editions=set() if no_pdf else wanted)


if __name__ == "__main__":
    main(sys.argv[1:])
