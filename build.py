#!/usr/bin/env python3
"""Weekly U.S. Economic Indicators — build script.

Usage:
  python3 build.py data/2026-09-23.json            # -> out/Economic_Report_2026-09-23.pdf + out/index.html
  python3 build.py data/2026-09-23.json --no-pdf   # site only

One data file feeds both outputs, so the PDF and the website can never disagree.
The archive of past editions lives in archive.json: [{"edition","label","pdf_url"}].
"""
import json, sys, os, html, pathlib, datetime

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"
FONTS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
         "&family=IBM+Plex+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&display=swap")

# ---------- formatting ----------
MINUS = "\u2212"
def fmt(v, kind):
    if v is None:
        return "—"
    if kind == "k":
        s = f"{abs(v):,.0f}"
    elif kind in ("pct", "pct1"):
        s = f"{abs(v):.1f}%"
    elif kind == "pct2":
        s = f"{abs(v):.2f}%"
    elif kind == "int":
        s = f"{abs(v):.0f}"
    elif kind == "m":
        s = f"{abs(v):.2f}"
    else:  # idx, b
        s = f"{abs(v):.1f}"
    return (MINUS + s) if v < 0 else s

def verdict(row, p):
    c, a, b = p["cons"], p["act"], row["better"]
    if c is None or a is None or b == "none" or a == c:
        return ""
    good = a > c if b == "higher" else a < c
    return "beat" if good else "miss"

esc = html.escape

# ---------- shared pieces ----------
def section_table(sec):
    rows = []
    for r in sec["rows"]:
        cells = []
        for p in (r["p1"], r["p2"]):
            v = verdict(r, p)
            cells.append(f'<td class="per">{esc(p["period"])}</td><td class="num">{fmt(p["cons"], r["fmt"])}</td>'
                         f'<td class="num act {v}">{fmt(p["act"], r["fmt"])}</td>')
        src = f'<a href="{esc(r["url"])}">{esc(r["src"])}</a>' if r["url"] else esc(r["src"])
        rows.append(f'<tr class="{"sub" if r["sub"] else ""}"><th scope="row">{esc(r["label"])}</th>{cells[0]}{cells[1]}'
                    f'<td class="note">{esc(r["note"])}</td><td class="src">{src}</td></tr>')
    return (f'<section class="block"><h2>{esc(sec["title"])}</h2><div class="scroll"><table>'
            '<colgroup><col class="c-ind"><col class="c-per"><col class="c-n"><col class="c-n"><col class="c-per"><col class="c-n"><col class="c-n"><col class="c-note"><col class="c-src"></colgroup>'
            '<thead><tr><th></th><th colspan="3" class="grp">Prior period</th><th colspan="3" class="grp">Latest period</th><th></th><th></th></tr>'
            '<tr><th>Indicator</th><th>Period</th><th>Cons.</th><th>Actual</th><th>Period</th><th>Cons.</th><th>Actual</th><th>Notes</th><th>Source</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')

def kpis(d):
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="kl">{esc(k["label"])}</div><div class="kv {k["tone"]}">{esc(k["value"])}</div>'
        f'<div class="kd">{esc(k["detail"])}</div></div>' for k in d["kpis"]) + "</div>"

def bottom(d):
    g = d["gdp"]
    qrows = "".join(f'<tr><th scope="row">{y}</th>' + "".join(f'<td class="num">{fmt(v,"pct")}</td>' for v in vals) + "</tr>"
                    for y, vals in g["years"].items())
    ulc = " · ".join(f"{k}: {v:.1f}%" for k, v in g["ulc"].items())
    eci = " · ".join(f"{k}: {v:.1f}%" for k, v in g["eci"].items())
    gdp = (f'<div class="card"><h3>Real GDP (QoQ SAAR)</h3><table class="mini"><thead><tr><th></th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th></tr></thead>'
           f'<tbody>{qrows}</tbody></table><p class="fine">GDPNow {esc(g["gdpnow"]["q"])}: <b>{g["gdpnow"]["value"]:.1f}%</b><br>'
           f'Unit labor costs (SAAR) — {ulc}<br>ECI (QoQ) — {eci}</p><p class="fine muted">{esc(g["note"])}</p>'
           '<p class="fine src"><a href="https://www.bea.gov/data/gdp/gross-domestic-product">BEA</a> · <a href="https://www.atlantafed.org/cqer/research/gdpnow">Atlanta Fed</a> · <a href="https://www.bls.gov/lpc/">BLS</a></p></div>')
    imf = "".join(f'<tr><th scope="row">{y}</th><td class="num">{u:.1f}%</td><td class="num">{w:.1f}%</td></tr>' for y, u, w in d["imf"]["rows"])
    ms = d["ms"]
    tgt = (f'<div class="card"><h3>Forecasts &amp; Targets</h3><table class="mini"><thead><tr><th>IMF GDP</th><th>U.S.</th><th>World</th></tr></thead><tbody>{imf}</tbody></table>'
           f'<p class="fine muted">{esc(d["imf"]["edition"])}</p>'
           f'<table class="mini"><tbody><tr><th scope="row">MS S&amp;P 500, YE 2026</th><td class="num">{ms["sp_ye26"]}</td></tr>'
           f'<tr><th scope="row">MS S&amp;P 500, mid-2027</th><td class="num">{ms["sp_mid27"]}</td></tr>'
           f'<tr><th scope="row">MS EPS 2026E / 2027E</th><td class="num">{ms["eps26"]} / {ms["eps27"]}</td></tr>'
           f'<tr><th scope="row">P/E on MS 2026E</th><td class="num">{ms["pe"]}</td></tr></tbody></table>'
           f'<p class="fine muted">{esc(ms["asof"])}. {esc(ms["note"])}</p>'
           '<p class="fine src"><a href="https://www.imf.org/en/Publications/WEO">IMF WEO</a> · public press coverage of MS Research</p></div>')
    m = d["markets"]
    mrows = "".join(f'<tr><th scope="row">{esc(n)}</th><td class="num">{esc(lvl)}</td><td class="num">{fmt(a,"pct")}</td>'
                    f'<td class="num {"beat" if b>=0 else "miss"}">{fmt(b,"pct")}</td></tr>' for n, lvl, a, b in m["rows"])
    rrows = "".join(f'<tr><th scope="row">{esc(n)}</th><td class="num">{a:.2f}%</td><td class="num">{b:.2f}%</td>'
                    f'<td class="num">{"+" if b>=a else MINUS}{abs(b-a)*100:.0f} bp</td></tr>' for n, a, b in m["rates"])
    mk = (f'<div class="card"><h3>Markets</h3><table class="mini"><thead><tr><th></th><th>Level</th><th>2025</th><th>YTD</th></tr></thead><tbody>{mrows}</tbody></table>'
          f'<table class="mini"><thead><tr><th></th><th>End-2025</th><th>Now</th><th>Chg</th></tr></thead><tbody>{rrows}</tbody></table>'
          f'<p class="fine muted">{esc(m["note"])}</p><p class="fine src"><a href="https://fred.stlouisfed.org/series/SP500">FRED</a> · <a href="https://home.treasury.gov/resource-center/data-chart-center/interest-rates">U.S. Treasury</a></p></div>')
    return f'<section class="bottom">{gdp}{tgt}{mk}</section>'

def story_watch(d):
    w = "".join(f"<li><span>{esc(a)}</span>{esc(b)}</li>" for a, b in d["watch"])
    return (f'<section class="sw"><div class="card story"><h3>The week in one paragraph</h3><p>{esc(d["story"])}</p></div>'
            f'<div class="card"><h3>On deck</h3><ul class="watch">{w}</ul></div></section>')

def method(d):
    return (f'<p class="method"><b>Method.</b> {esc(d["actuals_policy"])} {esc(d["consensus_policy"])} '
            '<span class="beat">Green</span> = better than consensus; <span class="miss">rust</span> = worse (for inflation, claims and '
            'unemployment, lower is better). Not investment advice.</p>')

CSS_BASE = """
:root{--ink:#13233a;--ink2:#2b3d57;--rule:#d7dce3;--soft:#eef1f5;--muted:#667489;--beat:#1f6b3a;--miss:#a63d1c;--paper:#fff;--accent:#b8862b}
*{box-sizing:border-box}
body{margin:0;font-family:"IBM Plex Sans",Arial,sans-serif;color:var(--ink);background:var(--paper)}
h1,h2,h3{font-family:"Source Serif 4",Georgia,serif;margin:0}
a{color:inherit}
.num,.kv,.per,td.num{font-family:"IBM Plex Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%}
.block h2{font-size:13px;color:var(--paper);background:var(--ink);padding:5px 10px;letter-spacing:.2px}
thead th{font-size:9px;font-weight:600;color:var(--muted);text-align:center;padding:3px 4px;border-bottom:1px solid var(--rule)}
thead th.grp{border-bottom:2px solid var(--accent);color:var(--ink2)}
thead tr:first-child th{border-bottom:none}
thead tr:first-child th.grp{border-bottom:2px solid var(--accent)}
thead th:first-child{text-align:left}
tbody th{text-align:left;font-weight:600;padding:3px 6px}
tbody td{text-align:center;padding:3px 4px}
tbody tr{border-bottom:1px solid var(--soft)}
tr.sub th{font-weight:400;font-style:italic;padding-left:20px;color:var(--ink2)}
td.act{font-weight:600}
.beat{color:var(--beat);font-weight:700}.miss{color:var(--miss);font-weight:700}
td.note{text-align:left;color:var(--muted);font-style:italic}
td.src{text-align:left;color:var(--muted)}
td.src a{text-decoration:none;border-bottom:1px dotted var(--muted)}
col.c-ind{width:21%}col.c-per{width:6.5%}col.c-n{width:6%}col.c-note{width:24%}col.c-src{width:10%}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:0;border-top:2px solid var(--ink);border-bottom:1px solid var(--rule)}
.kpi{padding:7px 10px;border-right:1px solid var(--rule)}.kpi:last-child{border-right:none}
.kl{font-size:9px;color:var(--muted)}
.kv{font-size:17px;font-weight:600;margin:2px 0}
.kv.up{color:var(--beat)}.kv.dn{color:var(--miss)}
.kd{font-size:9px;color:var(--ink2)}
.card h3{font-size:12.5px;border-bottom:2px solid var(--accent);padding-bottom:3px;margin-bottom:5px}
table.mini th,table.mini td{padding:2px 4px;font-size:9.5px}
table.mini thead th{font-size:8.5px}
.fine{font-size:8.5px;margin:4px 0 0;line-height:1.35}
.muted{color:var(--muted)}
.src a{color:var(--ink2)}
.watch{list-style:none;margin:0;padding:0}
.watch li{font-size:10px;padding:3px 0;border-bottom:1px solid var(--soft);display:flex;gap:10px}
.watch li span{font-family:"IBM Plex Mono",monospace;font-weight:600;min-width:62px}
.story p{font-family:"Source Serif 4",Georgia,serif;font-size:11px;line-height:1.5;margin:0}
.method{font-size:8px;color:var(--muted);line-height:1.4}
"""

# ---------- PDF ----------
def render_pdf_html(d):
    secs = d["sections"]
    css = CSS_BASE + """
@page{size:Letter;margin:0.32in 0.4in 0.32in}
body{font-size:9px}
.page{page-break-after:always}.page:last-child{page-break-after:auto}
header.mast{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:6px}
.mast h1{font-size:22px;letter-spacing:-.2px}
.mast .kick{font-size:9px;color:var(--muted);margin-bottom:2px}
.mast .date{text-align:right;font-size:10px}
.mast .date b{font-family:"Source Serif 4",serif;font-size:13px;display:block}
.block{margin-top:7px}
tbody th,tbody td{font-size:8.6px;padding-top:1.6px;padding-bottom:1.6px}
td.note,td.src{font-size:7.6px}
thead th{padding:2px 4px}
.block h2{padding:3px 10px;font-size:12px}
.bottom{display:grid;grid-template-columns:1fr 1fr 1.1fr;gap:14px;margin-top:8px}
.sw{display:grid;grid-template-columns:1.7fr 1fr;gap:14px;margin-top:8px}
.story p{font-size:9.6px;line-height:1.38}.watch li{font-size:8.6px;padding:1.5px 0}
.fine{font-size:7.8px;margin-top:3px}
table.mini th,table.mini td{padding:1.5px 4px;font-size:9px}
.card h3{font-size:11.5px;margin-bottom:3px}
.pagefoot{margin-top:5px}
.method{font-size:7.4px;margin:6px 0 0}
.pagefoot{display:flex;justify-content:space-between;font-size:8px;color:var(--muted);border-top:1px solid var(--rule);margin-top:8px;padding-top:4px}
"""
    mast = (f'<header class="mast"><div><div class="kick">Weekly briefing · two most recent releases per indicator</div>'
            f'<h1>U.S. Economic Indicators</h1></div><div class="date"><b>{esc(d["edition_label"])}</b>{esc(d["data_through"])}</div></header>')
    foot = lambda n: f'<div class="pagefoot"><span>U.S. Economic Indicators · {esc(d["edition"])}</span><span>Page {n} of 2</span></div>'
    p1 = f'<div class="page">{mast}{kpis(d)}{story_watch(d)}{section_table(secs[0])}{section_table(secs[1])}{section_table(secs[2])}{foot(1)}</div>'
    p2 = f'<div class="page">{section_table(secs[3])}{section_table(secs[4])}{bottom(d)}{method(d)}{foot(2)}</div>'
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{FONTS}"><style>{css}</style></head><body>{p1}{p2}</body></html>'

def build_pdf(d, html_path, pdf_path):
    from playwright.sync_api import sync_playwright
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.pdf(path=str(pdf_path), format="Letter", print_background=True, prefer_css_page_size=True)
        b.close()

# ---------- website ----------
def render_site(d, archive):
    latest = archive[0] if archive else None
    arch = "".join(f'<li><a href="{esc(a["pdf_url"])}" target="_blank" rel="noopener">{esc(a["label"])}</a>'
                   f'<button class="dl" data-url="{esc(a["pdf_url"])}" data-name="Economic_Report_{esc(a["edition"])}.pdf" hidden>Save</button></li>'
                   for a in archive)
    css = CSS_BASE + """
:root{--paper:#fbfaf7;--card:#fff}
:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ink:#e6ebf2;--ink2:#c2ccd9;--rule:#34404f;--soft:#27313d;--muted:#8d9bb0;--beat:#5cc98a;--miss:#f08a64;--paper:#141a22;--card:#1b232d;--accent:#d4a84a}}
:root[data-theme="dark"]{--ink:#e6ebf2;--ink2:#c2ccd9;--rule:#34404f;--soft:#27313d;--muted:#8d9bb0;--beat:#5cc98a;--miss:#f08a64;--paper:#141a22;--card:#1b232d;--accent:#d4a84a}
body{background:var(--paper);font-size:14px}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 48px}
header.mast{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:end;border-bottom:3px double var(--ink);padding-bottom:16px}
.mast h1{font-size:clamp(30px,5vw,52px);line-height:1;letter-spacing:-.8px}
.mast p{margin:8px 0 0;color:var(--muted);max-width:60ch}
.cta{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.btn{font:600 14px "IBM Plex Sans",sans-serif;background:var(--ink);color:var(--paper);border:0;border-radius:3px;padding:11px 18px;text-decoration:none;cursor:pointer}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--ink)}
.cta small{color:var(--muted);font-size:12px}
.kpis{margin-top:18px;background:var(--card)}
.kl{font-size:11.5px}.kv{font-size:24px}.kd{font-size:12px}
.block{margin-top:26px;background:var(--card)}
.block h2{font-size:16px;padding:8px 12px;background:var(--ink);color:var(--paper)}
.scroll{overflow-x:auto}
.scroll table{min-width:900px}
tbody th,tbody td{font-size:13px;padding:6px}
thead th{font-size:11px}
td.note,td.src{font-size:12px}
.bottom,.sw{display:grid;gap:22px;margin-top:28px}
.bottom{grid-template-columns:repeat(3,1fr)}.sw{grid-template-columns:1.6fr 1fr}
.card{background:var(--card);padding:14px 16px;border:1px solid var(--rule)}
.card h3{font-size:17px}
table.mini th,table.mini td{font-size:12.5px;padding:4px 6px}table.mini thead th{font-size:11px}
.fine{font-size:12px}.watch li{font-size:13.5px}.story p{font-size:16px;line-height:1.6;max-width:70ch}
.method{font-size:12px;margin-top:22px;max-width:100ch}
.archive{margin-top:30px}
.archive ol{list-style:none;padding:0;margin:0;columns:2;column-gap:28px}
.archive li{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--rule);break-inside:avoid}
.archive li a{font-family:"Source Serif 4",serif;font-size:16px;text-decoration:none}
.archive li a:hover{text-decoration:underline}
.dl{font:500 12px "IBM Plex Sans",sans-serif;background:none;border:1px solid var(--rule);color:var(--ink);border-radius:3px;padding:3px 10px;cursor:pointer}
@media(max-width:880px){.kpis{grid-template-columns:repeat(2,1fr)}.kpi{border-bottom:1px solid var(--rule)}.bottom,.sw{grid-template-columns:1fr}header.mast{grid-template-columns:1fr}.cta{align-items:flex-start}.archive ol{columns:1}}
"""
    dl = ""
    if latest:
        dl = (f'<div class="cta"><a class="btn" href="{esc(latest["pdf_url"])}" target="_blank" rel="noopener">Open this week\'s PDF</a>'
              f'<button class="btn ghost dl" data-url="{esc(latest["pdf_url"])}" data-name="Economic_Report_{esc(latest["edition"])}.pdf" hidden>Download PDF</button>'
              f'<small>Updated every Monday</small></div>')
    js = """
(async()=>{let dl=null;try{dl=await window.claude?.use?.("downloads")}catch(e){}
if(!dl)return;document.querySelectorAll("button.dl").forEach(b=>{b.hidden=false;b.addEventListener("click",async()=>{
const t=b.textContent;b.textContent="Preparing…";try{const r=await fetch(b.dataset.url);const blob=await r.blob();
await dl.save({filename:b.dataset.name,data:blob});}catch(e){window.open(b.dataset.url,"_blank")}b.textContent=t;})});})();
"""
    secs = "".join(section_table(s) for s in d["sections"])
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>U.S. Economic Indicators — {esc(d["edition_label"])}</title><link rel="stylesheet" href="{FONTS}">'
            f'<style>{css}</style></head><body><div class="wrap">'
            f'<header class="mast"><div><h1>U.S. Economic Indicators</h1><p>{esc(d["edition_label"])} edition · the two most recent releases for every '
            f'indicator, consensus vs. actual, each linked to its primary source. {esc(d["data_through"])}.</p></div>{dl}</header>'
            f'{kpis(d)}{story_watch(d)}{secs}{bottom(d)}{method(d)}'
            f'<section class="archive"><h2 style="font-size:24px;margin-bottom:8px">Past editions</h2><ol>{arch}</ol></section>'
            f'</div><script>{js}</script></body></html>')

def main():
    data_path = pathlib.Path(sys.argv[1])
    d = json.load(open(data_path))
    OUT.mkdir(exist_ok=True)
    arch_path = ROOT / "archive.json"
    archive = json.load(open(arch_path)) if arch_path.exists() else []
    if "--no-pdf" not in sys.argv:
        h = OUT / f"report_{d['edition']}.html"
        h.write_text(render_pdf_html(d))
        pdf = OUT / f"Economic_Report_{d['edition']}.pdf"
        build_pdf(d, h, pdf)
        print("PDF:", pdf)
    (OUT / "index.html").write_text(render_site(d, archive))
    print("Site:", OUT / "index.html")

if __name__ == "__main__":
    main()
