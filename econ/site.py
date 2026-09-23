"""Collect editions from data/ and write the static site.

Site layout (all links relative, so it works at a domain root or under /<repo>/):
  /                               latest edition
  /editions/<date>/               every edition
  /pdfs/Economic_Report_<date>.pdf
  /archive/                       all editions, newest first
  /methodology/
"""
import datetime as dt
import json
import os
import pathlib
import shutil

from .pdf import html_to_pdf
from .render import ROOT, pdf_path, render, site_css

DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"


def load_editions(data_dir=DATA_DIR, include_drafts=False):
    """All edition files, newest first. Drafts (status == 'draft') are skipped unless asked for."""
    eds = []
    for p in sorted(data_dir.glob("????-??-??.json")):
        d = json.loads(p.read_text())
        if d.get("status") == "draft" and not include_drafts:
            continue
        eds.append(d)
    return sorted(eds, key=lambda d: d["edition"], reverse=True)


def archive_entries(editions):
    out = []
    for d in editions:
        day = dt.date.fromisoformat(d["edition"])
        out.append({"edition": d["edition"], "label": f"{day:%B} {day.day}, {day.year}",
                    "year": day.year, "kpis": d["kpis"][:3]})
    return out


def sources(d):
    """Unique (src, url, [sections]) from an edition, in report order — for the methodology page."""
    seen = {}
    for sec in d["sections"]:
        for r in sec["rows"]:
            key = (r["src"], r["url"])
            seen.setdefault(key, [])
            if sec["title"] not in seen[key]:
                seen[key].append(sec["title"])
    return [{"src": s, "url": u, "sections": secs} for (s, u), secs in seen.items()]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build_site(editions, pdf_editions=(), site_dir=SITE_DIR):
    """Render every page. PDFs are (re)built only for editions listed in pdf_editions."""
    if not editions:
        raise SystemExit("No published editions found in data/.")
    for d in editions:
        if d["edition"] in pdf_editions:
            pdf = html_to_pdf(render("report_pdf.html", d=d), site_dir / pdf_path(d["edition"]))
            print("PDF: ", pdf.relative_to(ROOT))

    archive = archive_entries(editions)
    latest = editions[0]
    write(site_dir / "assets" / "site.css", site_css())
    write(site_dir / ".nojekyll", "")
    ctx = dict(archive=archive, latest=latest)
    write(site_dir / "index.html", render("edition.html", d=latest, root="", is_latest=True, **ctx))
    for d in editions:
        write(site_dir / "editions" / d["edition"] / "index.html",
              render("edition.html", d=d, root="../../", is_latest=d is latest, **ctx))
    write(site_dir / "archive" / "index.html", render("archive.html", root="../", **ctx))
    write(site_dir / "methodology" / "index.html",
          render("methodology.html", root="../", d=latest, sources=sources(latest), **ctx))
    # 404 is served at arbitrary paths, so it needs an absolute base (e.g. /econ-report/ on GitHub Pages).
    base = os.environ.get("SITE_BASE_PATH", "/").rstrip("/") + "/"
    write(site_dir / "404.html", render("404.html", root=base, **ctx))
    print("Site:", site_dir.relative_to(ROOT), f"({len(editions)} edition(s), latest {latest['edition']})")


def clean(site_dir=SITE_DIR):
    """Remove generated pages but keep previously built PDFs."""
    for p in site_dir.glob("*"):
        if p.name != "pdfs":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
