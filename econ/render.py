"""Jinja2 environment and page rendering. One data file feeds both the PDF and the site."""
import pathlib

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .formatting import bp_change, fmt, verdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

SITE = {"name": "U.S. Economic Indicators"}
FONTS_URL = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
             "&family=IBM+Plex+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&display=swap")


def pdf_path(edition):
    """Site-relative path of an edition's PDF (prefix with `root` in templates)."""
    return f"pdfs/Economic_Report_{edition}.pdf"


def env():
    e = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]),
                    undefined=StrictUndefined, trim_blocks=False, lstrip_blocks=False)
    e.filters["fmt"] = fmt
    e.globals.update(verdict=verdict, bp_change=bp_change, pdf_path=pdf_path,
                     site=SITE, fonts_url=FONTS_URL)
    return e


def site_css():
    return (TEMPLATES / "css" / "base.css").read_text() + (TEMPLATES / "css" / "site.css").read_text()


def render(template, **ctx):
    return env().get_template(template).render(**ctx)
