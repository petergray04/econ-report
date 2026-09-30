---
name: weekly-econ-edition
description: Produce the Monday edition of the U.S. Economic Indicators report in this repo — draft data/<date>.json from FRED, research every consensus and non-FRED actual from named public sources (published ranges allowed, never estimates), write KPIs/story/watch list, build and check the 2-page PDF, and open a pull request for Peter to approve. Use for "make this week's econ report", "run the Monday edition", or when the weekly routine fires.
---

# Weekly edition — U.S. Economic Indicators

You produce one edition end to end and hand it to Peter as a pull request. **You never merge and never publish.** Accuracy and sourcing beat completeness: an honest "—" is always better than a number you can't source.

Read `CLAUDE.md` (data rules) and `RUNBOOK.md` (release calendar, sources) first. Everything below is binding.

## Hard rules

1. **Never edit `data/2026-09-23.json`.** A test locks its hash.
2. **Actual = first print.** Use the value the agency published on release day. FRED rows come from `draft_edition.py` already. Put revisions in Notes (for example, "Jul rev. to +21K"), never in the Actual cell.
3. **YoY by date.** If an agency's release text disagrees with a computed figure, the release text wins.
4. **Consensus, in this order:**
   1. Bloomberg median as quoted in First Trust Data Watch. Use ftportfolios.com → Commentary → Economic Research, the first bullet: "…versus the consensus expected …".
   2. Dow Jones (CNBC/MarketWatch), Reuters/LSEG or FactSet. Name the source in Notes, e.g. "Consensus: LSEG".
   3. A **forecast range published by a named source**, e.g. "economists' estimates ranged from 3.2% to 3.5%". Write it as `"cons": {"lo": 3.2, "hi": 3.5}` and add `Cons. range: <source>` to Notes.
   4. Otherwise `null` ("—").
   - **Never compute, average, infer or make up a consensus or a range.** A range you built yourself from scattered forecasts counts as an estimate. Don't do it.
   - Many rows have no published forecast at all: manufacturing payrolls, capacity utilization, the MoM sub-rows, retail ex auto & gas, LEI, Case-Shiller, the mortgage rate, core PCE. `null` is the correct answer for them.
5. **Every number you enter must have a source you actually opened this session.** Record it in the PR's source log with the URL and the exact phrase you relied on. If sources conflict, or you can't open the primary source, keep the row's `needs_review` and explain why.
6. **Existing and pending home sales** come from NAR releases only. **Morgan Stanley** figures come from public press only, and the caveat text must stay.
7. **On deck (`watch`)** lists only dates confirmed on the agency's own release calendar.

## Procedure

### 1. Set up
```
pip install -r requirements.txt && python -m playwright install --with-deps chromium
```
`FRED_API_KEY` should be set in the environment. Without it the scripts still work, just more slowly.

### 2. Draft
```
python draft_edition.py --pr-body out/pr_body.md
```
This writes `data/<Monday>.json`:
- `"status": "draft"`
- new FRED first prints, with consensus `null` and `needs_review`
- refreshed markets
- flags on the manual rows

If the file already exists, stop and report. Don't overwrite it.

Health check:
```
python fetch_actuals.py --check data/2026-09-23.json
```
It must report 70/70. If it doesn't, stop and report which rows fail. Don't work around it.

### 3. Resolve every flagged row
Open `data/<date>.json` and go through each row with `needs_review`. Its `review` list says what's needed.

- **FRED rows with a new release:**
  - Find the consensus (rule 4).
  - Update Notes for the new release. Keep them short, because the PDF must stay at 2 pages.
  - If the review list mentions a revision, add it to Notes.
  - Check the first print against the agency release text. The release text wins.
- **Manual rows:**
  - Check whether a new release came out since the previous edition, using the source and timing in `econ/series.py` `MANUAL` and RUNBOOK.
  - If yes, move `p2` to `p1`, then fill the new `p2`: `period` in the same label style, `act` from the primary source, and `cons` per rule 4.
  - If no, leave the values alone.
- **When a row is fully sourced,** delete its `needs_review` and `review` keys.
- **When something can't be sourced,** leave the value `null` or unchanged and keep the flag. Replace `review` with one line saying what you tried.

### 4. Other blocks (the `draft_meta.todo` list)
- **`kpis`:** six headline prints from this edition's data. Use `"up"`, `"dn"` or `""` tone, and details like "vs +55K consensus". The KPI values must equal the table and markets numbers.
- **`story`:** one paragraph on what changed this week and why it matters. Use only facts that are in the edition.
- **`watch`:** the next 4–6 major releases, with dates confirmed on agency calendars (BLS, BEA, Census, Fed, UMich, ISM).
- **`gdp`, `imf`, `ms`:** update only if a new estimate, WEO or target was published, and source it.
- **Markets:** spot-check one index level against FRED and `data_through`. If it says `EFA/EEM: NOT REFRESHED`, fill the EFA/EEM closes from a public quote page and fix that text.

### 5. Finalize and build
```
python draft_edition.py --finalize data/<date>.json   # only succeeds when no needs_review remains
python validate.py --strict
python build.py
python -m pytest -q
```
- If the PDF has more than 2 pages, shorten Notes. Never change the CSS or drop rows.
- If some rows are still flagged, skip `--finalize`. The PR stays a draft and lists them.

### 6. Open the pull request (never merge)
```
git switch -c edition/<date>
git add data/<date>.json
git commit -m "Edition <date>"
git push -u origin edition/<date>
gh pr create --base main --title "Edition <date>" --body-file out/pr_final.md   # add --draft if anything is unresolved
```
Write `out/pr_final.md` with these sections:
1. **Summary:** what changed this week, in 2–3 lines.
2. **Needs your decision:** every row still flagged, and why.
3. **Source log:** a table with `Row | Period | Field | Value | Source (URL) | Exact quote`, covering every consensus, range and manual actual you entered.
4. **Checks:** health check 70/70, validate result, PDF page count, tests.

End by reporting the PR link and anything unresolved.
