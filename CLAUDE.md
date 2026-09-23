# U.S. Economic Indicators — Weekly Report Website

## What this project is

A public website that publishes a weekly U.S. economic indicators report every Monday.

Each edition covers about 45 indicators in five sections:
1. Labor Market
2. Personal / Household Sector
3. Industrial & Manufacturing
4. Housing
5. Inflation

It also has bottom blocks for GDP, forecasts and targets, and markets.

For every indicator, the report shows the **two most recent releases**. Each release shows period, consensus and actual. Every row also has a note and a link to its primary source.

Each edition ships as:
- a web page (the latest edition is the homepage),
- a downloadable 2-page PDF, and
- an entry in a "Past editions" archive.

The owner is Peter, a finance/econ student. The audience is financial advisors and finance readers. Accuracy and sourcing matter more than anything else on this site.

## Current state (v1 built 2026-09-23)

Repo: https://github.com/petergray04/econ-report (public) · Site: https://petergray04.github.io/econ-report/ (GitHub Pages, deployed by Actions)

| Path | Status |
|---|---|
| `data/2026-09-23.json` | First edition, fully researched and verified. **This is the data schema.** Never edit it; `tests/test_validate.py` locks its SHA-256. |
| `schema/edition.schema.json` | JSON Schema (2020-12) for every edition; `validate.py` adds the publish rules. |
| `build.py` + `econ/render.py`, `econ/site.py`, `econ/pdf.py`, `templates/` | Jinja2 build of the whole site into `site/`; PDFs must be exactly 2 Letter pages or the build fails. The archive is derived from `data/*.json` (drafts skipped). |
| `fetch_actuals.py` + `econ/fred.py`, `econ/series.py` | First prints from ALFRED. Uses `FRED_API_KEY` (env or git-ignored `.env`; GitHub secret for Actions), with a no-key fallback. `--check data/2026-09-23.json` → 70/70 match in both modes, 0 retries. |
| `draft_edition.py` + `econ/draft.py` | Monday draft (shift p2→p1, first prints, consensus null + `needs_review`, markets refresh); `--finalize`. |
| `.github/workflows/` | `deploy.yml` (push to main → Pages), `ci.yml` (PR checks), `monday-draft.yml` (cron Mon 10:00 UTC + dispatch → draft PR). |
| `RUNBOOK.md` | The Monday process for the PR-based workflow. |
| `out/` | Original pre-refactor outputs, kept as the visual reference. |

The Claude-artifact leftovers (`window.claude` downloads script, `/_blob/` URLs, `/opt/pw-browsers`) are gone, and `archive.json` has been removed.

Decisions made: GitHub Pages, public site, FRED API key provided, masthead name kept, no email signup in v1.

## Non-negotiable data rules (learned the hard way)

1. **Actual = first print.** Use the value as published on release day, taken from an ALFRED vintage, not today's revised value. Revisions go in the Notes column (e.g. "Jul rev. to +21K").
2. **Compute YoY by date, never by row offset.** FRED is missing the Oct-2025 observation because of the government shutdown. "12 rows back" silently produced CPI YoY of 3.7% when BLS published 3.4%. If a computed YoY ever differs from the agency's release text, the release text wins.
3. **Consensus policy, in this order:**
   1. Bloomberg median, as quoted in First Trust Data Watch (ftportfolios.com → Commentary → Economic Research, first bullet: "versus the consensus expected …").
   2. Otherwise Dow Jones (CNBC), Reuters/LSEG or FactSet. Name the source in Notes.
   3. Otherwise `null`, rendered as "—". **Never estimate or invent a consensus.**
4. **Market data:**
   - Index levels and returns come from FRED (`SP500`, `DJIA`, `NASDAQCOM`).
   - EFA/EEM come from the Yahoo chart API.
   - Treasury yields come from FRED (`DGS10`, `DGS30`).
   - Returns are price returns vs. the end-2025 close.
5. **Morgan Stanley figures are public press only.** Keep the caveat "confirm against internal research before client use".
6. **Existing home sales** are NAR-licensed and not in ALFRED. Take them from NAR releases.
7. **FRED rate-limits bursts (HTTP 503).**
   - Keep concurrency low (≈3–4 parallel requests).
   - Retry with backoff.
   - Sample vintages weekly, not daily, for monthly series.
   - Consider caching responses.
   - A FRED API key (free) would allow the proper ALFRED `realtime_start` / `vintage_dates` endpoints. That is cleaner and much faster. Adopt it if Peter provides a key via an env var.

## Data schema (see `data/2026-09-23.json`)

**Top-level keys:**
`edition`, `edition_label`, `data_through`, `sections[]`, `kpis[]`, `gdp`, `imf`, `ms`, `markets`, `watch[]`, `story`, `consensus_policy`, `actuals_policy`

**Section row fields:**
- `label`, `sub` (indented sub-row)
- `fmt`: one of `k`, `pct`, `pct1`, `pct2`, `int`, `idx`, `b`, `m`
- `better`: `higher`, `lower` or `none` (drives the green/rust beat/miss coloring)
- `note`, `src`, `url`
- `p1` and `p2` = `{period, cons, act}`, where p1 is the prior release and p2 is the latest

Add a JSON Schema file and validate every edition against it in CI.

## Target architecture (recommended — confirm with Peter before building)

**Static site, no server.**

**Generator.** Keep the Python generator, refactored into templates (Jinja2). Only move to Astro or Next if Peter wants richer interactivity. The Python build already produces the exact design.

**Site structure:**
```
/                      latest edition (web version of the report)
/editions/<date>/      each past edition's page
/pdfs/Economic_Report_<date>.pdf
/archive/              list of all editions, newest first
/methodology/          sources, consensus policy, first-print rule, disclaimer
```

**Hosting.** GitHub Pages, or Netlify/Vercel/Cloudflare Pages. Deploy on push to `main`.

**Monday automation (GitHub Actions):**
1. Cron at Monday 10:00 UTC runs `fetch_actuals.py`.
2. It creates `data/<date>.json` as a **draft**, copied from last week.
   - Rows with a new release get p2→p1 shifted and new actuals filled.
   - Consensus is left `null` and flagged `"needs_review": true`.
3. It opens a pull request with the draft plus a checklist of rows needing consensus or non-FRED actuals:
   - ISM, NFIB, NAHB, LEI, UMich, MBA, pending home sales, NAR.
4. Peter fills the gaps and merges.
5. The merge triggers: validate → build PDF + pages → deploy.

**Build requirements in CI:**
- Install Playwright Chromium.
- Fail the build if the PDF is not exactly 2 pages.
- Fail the build if any row lacks `src`/`url` or any `needs_review` flag remains.

Optional later: a small password-protected "editor" page for entering consensus instead of editing JSON.

## Design (keep it — Peter approved the current look)

**Tone.** Broadsheet / financial-briefing style.

**Fonts** (Google Fonts):
- Source Serif 4 for headings
- IBM Plex Sans for body text
- IBM Plex Mono with tabular numbers for all figures

**Palette:**
| Role | Color |
|---|---|
| Ink | `#13233a` |
| Accent gold rule | `#b8862b` |
| Beat | `#1f6b3a` |
| Miss | `#a63d1c` |
| Paper | `#fbfaf7` |

**Layout and behavior:**
- Dark mode via `prefers-color-scheme`.
- Tables scroll horizontally on mobile. The page itself never scrolls sideways.
- KPI strip of 6 tiles.
- "The week in one paragraph" + "On deck" watch list near the top.
- Methodology line at the bottom: green = better than consensus; for inflation, claims and unemployment, lower is better; not investment advice.

## Definition of done for v1

- [x] Repo builds locally with one command (`make build` or `python build.py data/<date>.json`).
- [x] The 2026-09-23 edition renders on the deployed site with identical numbers to `out/Economic_Report_2026-09-23.pdf`.
- [x] The PDF downloads from the site and the archive page lists it.
- [x] Methodology page exists.
- [x] `fetch_actuals.py` runs end-to-end without 503 failures and its output matches the verified numbers in `data/2026-09-23.json` for the FRED-covered rows. This is the regression test: e.g. Aug payrolls 162, Aug CPI YoY 3.4, Aug housing starts 1,275.
- [ ] The scheduled GitHub Action opens a draft PR on a manual trigger (`workflow_dispatch`).
- [x] JSON Schema validation runs in CI.
- [x] `RUNBOOK.md` is updated for the new workflow.

## Open decisions to ask Peter about (don't guess)

1. Hosting provider and domain name.
2. Public site, or restricted to a specific audience.
3. Whether he'll get a free FRED API key (recommended).
4. Branding: site name and any logo.
5. Whether he wants email signup / notification when a new edition posts (not in v1 unless requested).
