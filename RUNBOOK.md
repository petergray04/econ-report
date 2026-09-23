# Monday Routine — U.S. Economic Indicators

Target: new edition live by Monday 12:00 ET. Typical time: 30–45 minutes, most of it consensus sourcing.

Site: https://petergray04.github.io/econ-report/ · Repo: https://github.com/petergray04/econ-report

## How it works

```
Mon 10:00 UTC (6:00 ET)   GitHub Action "Monday draft"
                          ├─ health check: fetcher reproduces the verified 2026-09-23 edition
                          ├─ data/<Monday>.json drafted from last edition + FRED/ALFRED + markets
                          └─ opens a draft PR with a checklist of everything that needs you
You                       fill consensus + manual rows, finalize, push to the PR branch
Merge to main             GitHub Action "Build and deploy": tests → validate → build PDF + pages → GitHub Pages
```

Nothing is published until you merge. A file with `"status": "draft"` is never built or deployed. The deploy fails if any row still has `needs_review`, is missing a source, or if the PDF is not exactly 2 pages.

## Files

| Path | What it is |
|---|---|
| `data/YYYY-MM-DD.json` | The single source of truth for one edition. The PDF and the web page are both rendered from it. |
| `schema/edition.schema.json` | JSON Schema every edition must satisfy. |
| `draft_edition.py` | Drafts next week's file (`--finalize` clears the draft markers once review is done). |
| `fetch_actuals.py` | First-print actuals from FRED/ALFRED. `--check data/<date>.json` re-verifies an edition. |
| `validate.py` | Schema + publish rules. `--strict` = what the deploy enforces. |
| `build.py` | Builds `site/`: `/`, `/editions/<date>/`, `/archive/`, `/methodology/`, `/pdfs/`. |
| `templates/` | Jinja2 templates and CSS (the approved design). |
| `econ/` | The code behind the scripts. |

## One-time setup

```
make setup                         # venv, dependencies, Playwright Chromium
echo 'FRED_API_KEY=<your key>' > .env    # .env is git-ignored; never commit the key
gh secret set FRED_API_KEY         # paste the key when prompted; the Monday Action needs it
```

## Monday, step by step

### 1. Open the draft PR (≈1 min)

GitHub → Pull requests → **"Edition YYYY-MM-DD — draft for review"**. The PR description lists:
- **FRED rows with a new release.** These are already shifted (latest → prior) with the **first print** filled in. Consensus is `null`. If the prior release was revised, the checklist tells you what to put in Notes.
- **Manual rows**: ISM ×2, NFIB, LEI, UMich, NAHB, existing home sales (+ MoM), pending home sales, retail ex auto & gas. For each, check whether a new release came out since last edition.
- **Other blocks**: KPI strip, story, On deck, GDP, forecasts and targets, and a markets spot-check. Markets and `data_through` are already refreshed.

Check out the branch locally:
```
git fetch && git switch draft/<date>
```

If the draft didn't appear (for example, the Action failed), run it yourself:
```
python draft_edition.py --pr-body out/pr_body.md     # writes data/<next Monday>.json
```
You can also trigger it from GitHub: Actions → Monday draft → Run workflow.

### 2. Consensus and manual rows (≈25 min)

Consensus policy, in order of preference:
1. **Bloomberg median.** First Trust Data Watch quotes it in its first bullet ("…versus the consensus expected …"). See ftportfolios.com → Commentary → Economic Research.
2. **Dow Jones** (CNBC), **Reuters/LSEG** or **FactSet**, if Bloomberg isn't quoted. Name the source in Notes.
3. Otherwise **`null`**, which renders as "—". **Never estimate.**

For a manual row with a new release: move `p2` into `p1`, then fill the new `p2` (`period`, `cons`, `act`).

When a row is done, **delete its `"needs_review"` and `"review"` keys**.

| Row | Where the actual comes from | Release timing |
|---|---|---|
| Jobless claims | FRED (auto) · DOL weekly release (dol.gov/ui/data.pdf) | Thu 8:30 |
| ADP | FRED (auto) · adpemploymentreport.com | Wed before jobs report |
| UMich sentiment | sca.isr.umich.edu. Prelim on the 2nd Fri, final on the 4th Fri | Fri 10:00 |
| ISM Mfg / Services | ismworld.org | 1st and 3rd business day |
| NFIB | nfib.com SBET | 2nd Tue |
| Leading Economic Index | conference-board.org press release | ~3rd week |
| NAHB | nahb.org HMI | mid-month |
| Existing / pending home sales | nar.realtor newsroom (NAR-licensed; not in ALFRED) | — |
| Retail sales ex auto & gas | Census MARTS release table | mid-month |
| MBA applications (note) | mba.org weekly survey | Wed 7:00 |
| IMF WEO | imf.org. Jan / Apr / Jul / Oct | quarterly |
| Morgan Stanley targets | Public press only. Keep the "confirm against internal research" caveat. The schema enforces it. | as changed |

### 3. Headline strip, story, watch list (≈10 min)

- **`kpis`**: six headline prints. `"tone"` is `"up"`, `"dn"` or `""`.
- **`story`**: one paragraph on what changed this week and why it matters.
- **`watch`**: only release dates you have confirmed from the agency calendar.

### 4. Finalize, build, merge (≈5 min)

```
python draft_edition.py --finalize data/<date>.json   # refuses while any needs_review remains
make build                                            # validate + build; fails unless the PDF is 2 pages
make serve                                            # optional: preview at http://localhost:8765
```

- If the PDF spills to 3 pages, shorten Notes before touching the CSS.
- Spot-check five cells against their sources. Every row needs a `src` and a `url`.
- Commit, push to the PR branch, click **Ready for review**, then **Merge**. The site updates in about 2 minutes.

## Data rules (non-negotiable)

1. **Actual = first print.** Use the value published on release day, taken from an ALFRED vintage. `fetch_actuals.py` and the draft do this for you. Revisions go in Notes (for example, "Jul rev. to +21K").
   - Exception: *Core PCE (QoQ SAAR)* is shown at the current vintage, as the verified edition's note says.
2. **YoY is computed by date, never by row offset.** FRED has no Oct-2025 observation (shutdown). The code refuses to compute a MoM across a missing month rather than compare against the wrong one. If a computed figure differs from the agency's release text, the release text wins.
   - CPI and PPI YoY use the not-seasonally-adjusted index (`CPIAUCNS`, `CPILFENS`, `PPIFID`, `PPICOR`), as BLS does.
3. **Consensus**: see the policy above. Unknown = `null`.
4. **Markets**:
   - Index levels and YTD come from FRED (`SP500`, `DJIA`, `NASDAQCOM`).
   - EFA and EEM come from the Yahoo chart API.
   - Yields come from FRED (`DGS10`, `DGS30`).
   - Returns are price returns vs. the end-2025 close. Only completed sessions are used.
5. **`data/2026-09-23.json` is the verified reference edition. Never edit it.** A test locks its hash, and the Monday Action re-verifies the fetcher against it.

## Commands

| Command | What it does |
|---|---|
| `make build` | Validate every edition, then build all pages and PDFs into `site/` |
| `make site` | Pages only (reuses existing PDFs) |
| `make test` | Unit tests (offline). `FRED_LIVE=1 make test` adds the live FRED regression checks |
| `make fetch` | Latest two first prints for every FRED row → `out/actuals_<today>.csv` |
| `python fetch_actuals.py --check data/<date>.json` | Recompute an edition's FRED rows and compare |
| `python validate.py [--strict] [files]` | Schema + publish rules |
| `make serve` | Preview `site/` locally |

## Troubleshooting

- **FRED 503/429.** The client already keeps 3 requests in flight at most, spaces them 0.55 s apart, retries with backoff, and caches responses in `.cache/fred/`. Just re-run; cached responses aren't re-fetched. Without `FRED_API_KEY` it falls back to weekly ALFRED sampling. That's slower (≈400 requests on a cold cache) but gives the same numbers.
- **Health check failed in the Monday Action.** A FRED series was redefined or renamed. Run `python fetch_actuals.py --check data/2026-09-23.json -v` locally and look at the ✗ rows. Fix the mapping in `econ/series.py`, never the data.
- **EFA/EEM not refreshed.** The Yahoo API is unofficial. The draft says `EFA/EEM: NOT REFRESHED` in `data_through`. Enter the closes by hand and fix that line.
- **Deploy failed.** Open the Action log. The failing step names the edition and the row: validation, 2-page check, or tests.
- **Correcting a published edition.** Edit its data file in a PR and merge. Every page and PDF is rebuilt on deploy. Put the correction in Notes.
