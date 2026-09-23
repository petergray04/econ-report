"""HTML -> PDF via Playwright/Chromium, with the hard 2-page Letter check."""
import pathlib
import tempfile

from pypdf import PdfReader

REQUIRED_PAGES = 2


class PageCountError(RuntimeError):
    pass


def html_to_pdf(html, pdf_path):
    from playwright.sync_api import sync_playwright

    pdf_path = pathlib.Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / "report.html"
        src.write_text(html)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(src.as_uri(), wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.pdf(path=str(pdf_path), format="Letter", print_background=True, prefer_css_page_size=True)
            b.close()
    check_pages(pdf_path)
    return pdf_path


def check_pages(pdf_path):
    n = len(PdfReader(str(pdf_path)).pages)
    if n != REQUIRED_PAGES:
        raise PageCountError(f"{pdf_path.name} has {n} pages; it must be exactly {REQUIRED_PAGES} Letter pages. "
                             "Shorten Notes before touching the CSS.")
    return n
