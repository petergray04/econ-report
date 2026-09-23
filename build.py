#!/usr/bin/env python3
"""Weekly U.S. Economic Indicators — build script.

Usage:
  python3 build.py data/2026-09-23.json            # -> site/index.html + site/pdfs/Economic_Report_2026-09-23.pdf
  python3 build.py data/2026-09-23.json --no-pdf   # site only

One data file feeds both outputs, so the PDF and the website can never disagree.
The build fails if the PDF is not exactly 2 Letter pages.
"""
import json
import pathlib
import sys

from econ.pdf import html_to_pdf
from econ.render import ROOT, pdf_path, render, site_css

SITE_DIR = ROOT / "site"


def main():
    data_path = pathlib.Path(sys.argv[1])
    d = json.loads(data_path.read_text())
    archive = json.loads((ROOT / "archive.json").read_text())
    SITE_DIR.mkdir(exist_ok=True)
    if "--no-pdf" not in sys.argv:
        pdf = html_to_pdf(render("report_pdf.html", d=d), SITE_DIR / pdf_path(d["edition"]))
        print("PDF:", pdf)
    (SITE_DIR / "assets").mkdir(exist_ok=True)
    (SITE_DIR / "assets" / "site.css").write_text(site_css())
    (SITE_DIR / "index.html").write_text(render("edition.html", d=d, archive=archive, root=""))
    print("Site:", SITE_DIR / "index.html")


if __name__ == "__main__":
    main()
