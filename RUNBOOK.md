# Monday Routine — U.S. Economic Indicators

Target: new edition live by Monday 12:00 ET. Typical time: 45–60 minutes.

## Files

| File | What it is |
|---|---|
| `data/YYYY-MM-DD.json` | The single source of truth for one edition. Both the PDF and the website are rendered from it. |
| `fetch_actuals.py` | Pulls first-print actuals from FRED/ALFRED and market levels. No API key. |
| `build.py` | Renders `out/Economic_Report_YYYY-MM-DD.pdf` (2 pages, Letter) and `out/index.html` (website). |
| `archive.json` | List of past editions and their PDF links; the website's "Past editions" list is built from it. |

Setup (once): `pip install playwright pypdf && python -m playwright install chromium`

## Step 1 — Pull actuals (≈5 min)

```
python3 fetch_actuals.py
```

This writes `out/actuals_YYYY-MM-DD.csv` with, for every FRED-covered row, the two latest observations, the **first print** (the value on release day) and the **current** (revised) value.

Rules:
- The report's **Actual** is always the first print. If a later release revised it, keep the first print and put the revision in Notes (e.g. "Jul rev. to +21K").
- CPI/PPI/PCE **YoY** must match the percentage in the BLS/BEA release text. The script computes YoY by date; if it ever disagrees with the release, the release wins.
- Existing home sales are NAR-licensed and not in ALFRED; take them from the NAR release.

## Step 2 — Copy last week's data file

```
cp data/<last-monday>.json data/<today>.json
```

For each row, ask: *did a new release come out since last Monday?*
- **Yes** → shift the old "latest" (p2) into "prior" (p1) and fill the new p2.
- **No** → leave the row alone.

Update `edition`, `edition_label` and `data_through`.

## Step 3 — Consensus and non-FRED rows (≈25 min)

Consensus policy, in order of preference:
1. **Bloomberg median.** First Trust Data Watch quotes it in its first bullet ("…versus the consensus expected …"). See ftportfolios.com → Commentary → Economic Research.
2. **Dow Jones** (CNBC), **Reuters/LSEG**, or **FactSet**, if Bloomberg isn't quoted. Say which in Notes.
3. **"—"** (`null` in the JSON) if no public consensus exists. Never estimate.

| Row | Where the actual comes from | Release timing |
|---|---|---|
| Jobless claims | DOL weekly release (dol.gov/ui/data.pdf) | Thu 8:30 |
| ADP | adpemploymentreport.com | Wed before jobs report |
| UMich sentiment | sca.isr.umich.edu — prelim on the 2nd Fri, final on the 4th Fri | Fri 10:00 |
| ISM Mfg / Services | ismworld.org | 1st and 3rd business day |
| NFIB | nfib.com SBET | 2nd Tue |
| Leading Economic Index | conference-board.org press release | ~3rd week |
| NAHB | nahb.org HMI | mid-month |
| Existing / pending home sales | nar.realtor newsroom | — |
| MBA applications | mba.org weekly survey | Wed 7:00 |
| IMF WEO | imf.org — Jan / Apr / Jul / Oct | quarterly |
| Morgan Stanley targets | public press only. Keep the "confirm against internal research" caveat. | as changed |

## Step 4 — Headline strip, story, watch list (≈10 min)

- **`kpis`**: six headline prints. Use `"up"` or `"dn"` for the tone.
- **`story`**: one paragraph covering what changed this week and why it matters.
- **`watch`**: only release dates you have confirmed from the agency calendar.

## Step 5 — Build and check (≈5 min)

```
python3 build.py data/<today>.json
```

- The PDF must be exactly 2 pages. If it spills over, shorten Notes before touching the CSS.
- Spot-check five cells against their sources.
- Every row needs a source.

## Step 6 — Publish

1. Upload the PDF to the site's asset store. In a Claude chat, say:
   "Upload out/Economic_Report_<date>.pdf to my econ report site and add it to the archive."
2. Add the entry at the top of `archive.json`:
   ```
   {"edition": "<date>", "label": "<Month D, YYYY>", "pdf_url": "/_blob/<asset id>"}
   ```
3. Rebuild with `python3 build.py data/<today>.json --no-pdf` and republish `out/index.html` to the same site URL.

If the site moves to your own domain, set `pdf_url` to a relative path (for example `pdfs/Economic_Report_<date>.pdf`) and upload the PDF next to `index.html`.
