# How the PDF download system works

Each edition of the report ships as a web page **and** a 2-page Letter PDF that readers can download. This document explains how the PDF is made, where it lives, how the links find it, and what keeps it from breaking.

## The short version

```
data/<date>.json ──► Jinja2 template ──► HTML ──► Chromium (Playwright) ──► PDF
                    (report_pdf.html)                  page.pdf()          │
                                                                           ▼
                                               pypdf: exactly 2 pages? ── no ──► build fails
                                                                           │ yes
                                                                           ▼
                                        site/pdfs/Economic_Report_<date>.pdf
                                                                           │
             every page links to it with a relative <a href="…pdf" download>
                                                                           │
                         GitHub Actions uploads site/ ──► GitHub Pages serves it
```

There is no server, no database and no download script. The PDF is a static file sitting next to the HTML pages. The browser downloads it with a plain link.

---

## 1. One data file, two outputs

`data/<date>.json` is the single source of truth for an edition. The PDF and the web page are both rendered from it by the same shared template macros (`templates/_macros.html`), so they can't show different numbers.

| Output | Template | Written to |
|---|---|---|
| Web page | `templates/edition.html` | `site/index.html` (latest) and `site/editions/<date>/index.html` |
| PDF | `templates/report_pdf.html` + `css/pdf.css` | `site/pdfs/Economic_Report_<date>.pdf` |

The PDF template is the print layout:
- Page 1 holds the masthead, the KPI strip, the story, the watch list and the first three sections.
- Page 2 holds the last two sections, the GDP, forecasts and markets blocks, and the Method line.
- `@page { size: Letter }` sets the paper size, and `page-break-after` separates the two pages.

## 2. Turning HTML into a PDF (`econ/pdf.py`)

`html_to_pdf(html, pdf_path)` does this:

1. **Writes the rendered HTML to a temporary file.** Chromium needs a real `file://` URL to load it.
2. **Launches headless Chromium through Playwright** and opens that file.
3. **Waits for `networkidle` and then `document.fonts.ready`.** The fonts (Source Serif 4, IBM Plex Sans, IBM Plex Mono) load from Google Fonts. Printing before they arrive would use fallback fonts, which have different widths and could push content onto a third page.
4. **Calls `page.pdf(format="Letter", print_background=True, prefer_css_page_size=True)`.**
   - `print_background` keeps the dark section headers and the colored cells.
   - `prefer_css_page_size` makes the CSS `@page` rule decide the page size and margins.
5. **Deletes the temporary HTML file.**
6. **Runs `check_pages()`.**

### The 2-page rule

`check_pages()` opens the finished PDF with **pypdf** and counts its pages. If the count isn't exactly 2, it raises `PageCountError`, which stops the whole build.

This check runs everywhere the PDF is built: locally with `make build`, on pull requests, and before every deploy. A PDF that spills onto a third page can't reach the site. The fix is to shorten the Notes text, not to change the CSS.

## 3. Where the file lives: one path convention

A single function in `econ/render.py` decides every PDF's location:

```python
def pdf_path(edition):
    return f"pdfs/Economic_Report_{edition}.pdf"
```

The PDF builder writes to `site/` + `pdf_path(date)`, and every template link reads from `root` + `pdf_path(date)`. Because both sides use the same function, the link and the file can't disagree.

### Relative links (`root`)

Pages sit at different depths, so each page is rendered with a `root` prefix that leads back to the site root:

| Page | `root` | Resulting PDF link |
|---|---|---|
| `/` (homepage) | `""` | `pdfs/Economic_Report_2026-09-23.pdf` |
| `/archive/`, `/methodology/` | `"../"` | `../pdfs/Economic_Report_2026-09-23.pdf` |
| `/editions/<date>/` | `"../../"` | `../../pdfs/Economic_Report_2026-09-23.pdf` |

Relative links mean the site works unchanged at any address:
- a domain root like `https://example.com/`
- a GitHub Pages subpath like `https://petergray04.github.io/econ-report/`
- `localhost` during `make serve`

The only exception is `404.html`. It can be served at any broken URL, so relative links would point to the wrong place. It uses an absolute base taken from the `SITE_BASE_PATH` environment variable, which the deploy workflow sets to `/econ-report/`.

## 4. The download links themselves

Each edition page has two buttons:

```html
<a class="btn" href="pdfs/Economic_Report_2026-09-23.pdf" download>Download PDF</a>
<a class="btn ghost" href="pdfs/Economic_Report_2026-09-23.pdf" target="_blank" rel="noopener">Open PDF</a>
```

- **`download` attribute:** tells the browser to save the file instead of showing it. This works because the PDF is on the same site as the page.
- **`target="_blank"`:** opens the PDF in a new tab for reading. `rel="noopener"` stops that new tab from controlling the page that opened it.

The **Past editions** list on each edition page and the **Archive** page link to every edition's web page plus a small `PDF` download link built the same way.

### Why plain links

The original version was hosted as a Claude artifact. There, downloads needed a JavaScript bridge (`window.claude.use("downloads")`), and PDFs lived at private `/_blob/<id>` URLs. That setup doesn't work on a normal website, so it was removed:
- There's no JavaScript involved in downloading, which means nothing that can fail.
- A test (`tests/test_render.py::test_no_claude_artifact_leftovers`) fails if `window.claude` or `/_blob/` ever reappears. The same test confirms the download link is present.

## 5. How the archive knows which PDFs exist

There's no hand-maintained list. `econ/site.py` builds the archive from the data folder:

1. `load_editions()` reads every `data/YYYY-MM-DD.json`.
2. It **skips drafts** (`"status": "draft"`), so an unfinished edition never gets a page or a PDF link.
3. It sorts the editions newest first. The newest becomes the homepage.
4. `archive_entries()` turns each edition into a label such as "September 23, 2026", with its year and first three KPIs for the archive page.

Adding a published data file therefore adds its page, its PDF and its archive entry in one step. The old `archive.json` was removed because it could drift out of sync.

## 6. Building: which PDFs get made (`build.py`)

| Command | Pages | PDFs |
|---|---|---|
| `python build.py` / `make build` | all | **rebuilt for every published edition** |
| `python build.py data/<date>.json` | all | rebuilt for that edition only |
| `python build.py --no-pdf` / `make site` | all | none; existing files in `site/pdfs/` are reused |

Before rendering, `clean()` deletes the generated pages in `site/` but **keeps `site/pdfs/`**, so a pages-only rebuild doesn't lose PDFs. `site/` is git-ignored: PDFs are never committed and are always rebuilt from data.

## 7. Getting the files online (GitHub Actions → GitHub Pages)

On every push to `main`, `.github/workflows/deploy.yml` runs these steps:

1. Installs Python dependencies and Playwright's Chromium (`playwright install --with-deps chromium`).
2. Runs the tests, then `validate.py --strict`. This step fails on drafts, leftover `needs_review` flags and rows with no source.
3. Runs `configure-pages`, which supplies the `/econ-report/` base path used by `404.html`.
4. Runs `python build.py`, which builds every page and every PDF and applies the 2-page check to each.
5. Uploads `site/` as the Pages artifact and deploys it.

GitHub Pages serves `.pdf` files as `application/pdf`, so browsers handle both buttons correctly.

Because CI rebuilds every PDF from data on each deploy, fixing a published edition means editing its data file and merging. Its PDF is regenerated automatically.

## 8. What can go wrong, and what catches it

| Problem | What catches it |
|---|---|
| PDF spills onto a 3rd page (long notes, wide ranges) | `check_pages()` → build fails locally, on the PR and before deploy |
| Link points to a file that doesn't exist | Both come from `pdf_path()`; the archive is built from the same data files as the PDFs |
| Draft edition gets published | `load_editions()` skips drafts; `validate.py --strict` fails the deploy |
| Old Claude-host download code returns | `test_no_claude_artifact_leftovers` |
| Fonts not loaded when printing | Wait for `networkidle` + `document.fonts.ready` before `page.pdf()` |
| Site moved to a new domain or subpath | Relative `root` links; only `404.html` needs `SITE_BASE_PATH` |

## Files involved

| File | Role |
|---|---|
| `build.py` | CLI: which editions get PDFs |
| `econ/site.py` | Loads editions, builds the archive, writes every page and PDF |
| `econ/pdf.py` | HTML → PDF with Playwright; 2-page check with pypdf |
| `econ/render.py` | Jinja2 setup; `pdf_path()` |
| `templates/report_pdf.html`, `templates/css/pdf.css` | The print layout |
| `templates/edition.html`, `templates/archive.html` | Download and archive links |
| `.github/workflows/deploy.yml` | Builds and publishes to GitHub Pages |
