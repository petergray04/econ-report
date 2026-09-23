"""Which report rows come from FRED, and how to turn a series into the number the report shows.

Rows are identified by a stable key: the row label, prefixed with its parent row for sub-rows
("Housing Starts (000s) › % Month over Month"), because several sub-row labels repeat.

Rules baked in here (see CLAUDE.md):
  * Actual = FIRST PRINT: the value on the day the observation was first published (ALFRED),
    computed from the series exactly as it stood that day (so MoM uses the then-current prior month).
  * Every comparison is BY DATE: previous month/quarter/week and same month last year are looked up
    by calendar date, never by row offset. A missing observation (e.g. Oct-2025, government
    shutdown) yields None instead of silently comparing against the wrong period.
  * YoY for CPI/PPI uses the NOT seasonally adjusted index, as BLS does in its headline 12-month change.
"""
import datetime as dt
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .fred import Fred, FredError, snapshot


@dataclass(frozen=True)
class Spec:
    sid: str
    kind: str = "lvl"          # lvl | diff | mom | yoy
    scale: float = 1.0
    mode: str = "first"        # first = first print (ALFRED); current = today's vintage


# row key -> Spec.  Rows not listed here are entered by hand (see MANUAL).
ROWS = {
    "Initial Jobless Claims (000s)": Spec("ICSA", "lvl", 0.001),
    "Continuing Claims (000s)": Spec("CCSA", "lvl", 0.001),
    "ADP Private Employment (000s)": Spec("ADPMNUSNERSA", "diff", 0.001),
    "Nonfarm Payrolls (000s)": Spec("PAYEMS", "diff"),
    "Nonfarm Payrolls (000s) › Private Payrolls": Spec("USPRIV", "diff"),
    "Nonfarm Payrolls (000s) › Manufacturing Payrolls": Spec("MANEMP", "diff"),
    "Unemployment Rate": Spec("UNRATE"),
    "JOLTS Job Openings (000s)": Spec("JTSJOL"),
    "Consumer Credit ($B)": Spec("TOTALSL", "diff", 0.001),
    "Personal Income (MoM)": Spec("PI", "mom"),
    "Personal Spending (MoM)": Spec("PCE", "mom"),
    "Retail Sales (MoM)": Spec("RSAFS", "mom"),
    "Industrial Production (MoM)": Spec("INDPRO", "mom"),
    "Capacity Utilization": Spec("TCU"),
    "Durable Goods Orders (MoM)": Spec("DGORDER", "mom"),
    "Factory Orders (MoM)": Spec("AMTMNO", "mom"),
    "Construction Spending (MoM)": Spec("TTLCONS", "mom"),
    "Housing Starts (000s)": Spec("HOUST"),
    "Housing Starts (000s) › % Month over Month": Spec("HOUST", "mom"),
    "Building Permits (000s)": Spec("PERMIT"),
    "Building Permits (000s) › % Month over Month": Spec("PERMIT", "mom"),
    "New Home Sales (000s)": Spec("HSN1F"),
    "New Home Sales (000s) › % Month over Month": Spec("HSN1F", "mom"),
    "Case-Shiller 20-City (YoY, NSA)": Spec("SPCS20RNSA", "yoy"),
    "Freddie Mac 30-Yr Mortgage": Spec("MORTGAGE30US"),
    "CPI (MoM)": Spec("CPIAUCSL", "mom"),
    "CPI (YoY)": Spec("CPIAUCNS", "yoy"),
    "CPI (YoY) › Ex Food & Energy (MoM)": Spec("CPILFESL", "mom"),
    "CPI (YoY) › Ex Food & Energy (YoY)": Spec("CPILFENS", "yoy"),
    "PPI Final Demand (MoM)": Spec("PPIFIS", "mom"),
    "PPI Final Demand (YoY)": Spec("PPIFID", "yoy"),
    "PPI Final Demand (YoY) › Ex Food & Energy (MoM)": Spec("PPIFES", "mom"),
    "PPI Final Demand (YoY) › Ex Food & Energy (YoY)": Spec("PPICOR", "yoy"),
    "Core PCE (YoY)": Spec("PCEPILFE", "yoy"),
    # The verified edition shows this row at the CURRENT vintage (its note says so), so we match that.
    "Core PCE (QoQ SAAR)": Spec("DPCCRV1Q225SBEA", "lvl", mode="current"),
}

# Rows whose actual (and all consensus) must be entered by hand, with where to get them.
MANUAL = {
    "UMich Consumer Sentiment": "UMich SCA (sca.isr.umich.edu) — prelim 2nd Fri, final 4th Fri",
    "Retail Sales (MoM) › Ex Auto & Gas": "Census MARTS release table",
    "ISM Manufacturing PMI": "ISM (ismworld.org) — 1st business day",
    "ISM Services PMI": "ISM (ismworld.org) — 3rd business day",
    "NFIB Small Business Optimism": "NFIB SBET — 2nd Tue",
    "Leading Economic Index (MoM)": "Conference Board press release",
    "NAHB Housing Market Index": "NAHB HMI — mid-month",
    "Existing Home Sales (mil.)": "NAR release (licensed; not in ALFRED)",
    "Existing Home Sales (mil.) › % Month over Month": "NAR release",
    "Pending Home Sales (MoM)": "NAR release",
}

# Extra figures that feed Notes / bottom blocks (reported in the CSV, not auto-filled).
EXTRAS = {
    "U-6 rate (note)": Spec("U6RATE"),
    "Participation (note)": Spec("CIVPART"),
    "Durables ex-transport (note)": Spec("ADXTNO", "mom"),
    "Real GDP QoQ SAAR (GDP block)": Spec("A191RL1Q225SBEA", mode="current"),
    "Unit labor costs (GDP block)": Spec("PRS85006112", mode="current"),
    "GDPNow (GDP block)": Spec("GDPNOW", mode="current"),
    "10-Yr Treasury (markets)": Spec("DGS10", mode="current"),
    "30-Yr Treasury (markets)": Spec("DGS30", mode="current"),
    "Fed funds upper (KPI)": Spec("DFEDTARU", mode="current"),
    "Existing home sales, mil. (check only — NAR is the source)": Spec("EXHOSLUSM495S", "lvl", 1e-6, mode="current"),
}
MARKETS = {"S&P 500": "SP500", "Dow Jones": "DJIA", "NASDAQ Comp.": "NASDAQCOM"}

# Display precision per fmt, for comparing a computed value with a published one.
DECIMALS = {"k": 0, "int": 0, "pct": 1, "pct1": 1, "pct2": 2, "idx": 1, "b": 1, "m": 2}


def round_half_up(v, places):
    if v is None:
        return None
    return float(Decimal(repr(v)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)) + 0.0  # no -0.0


# ---------- row keys ----------
def row_keys(section):
    """Yield (key, row) for a section's rows, qualifying sub-rows with their parent label."""
    parent = None
    for r in section["rows"]:
        if not r["sub"]:
            parent = r["label"]
            yield r["label"], r
        else:
            yield f"{parent} › {r['label']}", r


# ---------- dates & periods ----------
def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1)


def infer_freq(dates):
    ds = sorted(dt.date.fromisoformat(x) for x in dates)[-6:]
    gaps = sorted((b - a).days for a, b in zip(ds, ds[1:]))
    g = gaps[len(gaps) // 2] if gaps else 30
    return "W" if g <= 8 else "Q" if g >= 80 else "M"


def prev_date(obs, freq):
    d = dt.date.fromisoformat(obs)
    if freq == "W":
        return (d - dt.timedelta(days=7)).isoformat()
    return add_months(d, -3 if freq == "Q" else -1).isoformat()


def year_ago(obs):
    return f"{int(obs[:4]) - 1}{obs[4:]}"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def period_label(obs, freq, style):
    """Observation date -> the label style used in the data file ('Aug', 'Wk 9/12', '9/17', 'Q2')."""
    d = dt.date.fromisoformat(obs)
    if style == "week":
        return f"Wk {d.month}/{d.day}"
    if style == "date":
        return f"{d.month}/{d.day}"
    if freq == "Q" or style == "quarter":
        return f"Q{(d.month - 1) // 3 + 1}"
    return MONTHS[d.month - 1]


def period_style(label):
    if label.startswith("Wk "):
        return "week"
    if re.fullmatch(r"\d{1,2}/\d{1,2}", label):
        return "date"
    if re.fullmatch(r"Q[1-4]", label):
        return "quarter"
    return "month"


def period_to_obs(label, edition):
    """'Aug' / 'Wk 9/12' / '9/17' / 'Q2' -> FRED observation date, the latest such period before the edition."""
    ed = dt.date.fromisoformat(edition)
    m = re.fullmatch(r"(?:Wk )?(\d{1,2})/(\d{1,2})", label)
    if m:
        d = dt.date(ed.year, int(m[1]), int(m[2]))
        return (d if d <= ed else d.replace(year=ed.year - 1)).isoformat()
    m = re.fullmatch(r"Q([1-4])", label)
    if m:
        d = dt.date(ed.year, 3 * int(m[1]) - 2, 1)
        return (d if d <= ed else d.replace(year=ed.year - 1)).isoformat()
    if label in MONTHS:
        d = dt.date(ed.year, MONTHS.index(label) + 1, 1)
        return (d if d <= ed else d.replace(year=ed.year - 1)).isoformat()
    return None  # e.g. 'Aug (F)' — not a FRED period


# ---------- transforms ----------
def transform(snap, obs, kind, scale, freq):
    """Value shown in the report for `obs`, computed BY DATE from one snapshot of the series."""
    if obs not in snap:
        return None
    if kind == "lvl":
        return snap[obs] * scale
    if kind == "yoy":
        base = year_ago(obs)
        return (snap[obs] / snap[base] - 1) * 100 if base in snap else None
    prev = prev_date(obs, freq)
    if prev not in snap:
        return None       # e.g. Nov-2025 vs missing Oct-2025: refuse rather than compare to Sep
    if kind == "diff":
        return (snap[obs] - snap[prev]) * scale
    if kind == "mom":
        return (snap[obs] / snap[prev] - 1) * 100
    raise ValueError(kind)


@dataclass
class Print:
    obs: str                 # observation date (YYYY-MM-DD)
    release: str | None      # first day this observation was published (None for current mode)
    first: float | None      # value the report shows (first print, or current for mode=current)
    current: float | None    # today's (possibly revised) value
    freq: str


class Fetcher:
    def __init__(self, fred=None):
        self.fred = fred or Fred()
        self._hist, self._cur = {}, {}

    def _start(self, obs_dates):
        return add_months(dt.date.fromisoformat(min(obs_dates)), -15).isoformat()

    def current_series(self, sid, start):
        key = (sid, start)
        if key not in self._cur:
            self._cur[key] = self.fred.current(sid, start)
        return self._cur[key]

    def latest_obs(self, spec, n=2):
        start = add_months(dt.date.today(), -20).isoformat()
        cur = self.current_series(spec.sid, start)
        return sorted(cur)[-n:]

    def prints(self, spec, obs_dates):
        """Print for each observation date (first print unless spec.mode == 'current')."""
        start = self._start(obs_dates)
        cur = self.current_series(spec.sid, start)
        freq = infer_freq(cur)
        out = []
        if spec.mode == "current":
            for o in obs_dates:
                v = transform(cur, o, spec.kind, spec.scale, freq)
                out.append(Print(o, None, v, v, freq))
            return out
        if self.fred.key:
            if (spec.sid, start) not in self._hist:
                self._hist[(spec.sid, start)] = self.fred.vintages(spec.sid, start)
            hist = self._hist[(spec.sid, start)]
            for o in obs_dates:
                periods = [p for p in hist.get(o, []) if p[2] is not None]
                release = periods[0][0] if periods else None
                if release is not None and release <= start:
                    raise FredError(f"{spec.sid} {o}: first print predates the query window")
                first = transform(snapshot(hist, release), o, spec.kind, spec.scale, freq) if release else None
                out.append(Print(o, release, first, transform(cur, o, spec.kind, spec.scale, freq), freq))
            return out
        return self._prints_sampled(spec, obs_dates, start, cur, freq)

    def _prints_sampled(self, spec, obs_dates, start, cur, freq):
        """No API key: sample ALFRED weekly and take the first sample that contains the observation."""
        first_obs = dt.date.fromisoformat(min(obs_dates))
        v = first_obs + dt.timedelta(days=1)
        samples = []
        while v < dt.date.today():
            samples.append(v.isoformat())
            v += dt.timedelta(days=7)
        samples.append(dt.date.today().isoformat())   # always include today's vintage
        out = []
        for o in obs_dates:
            found = None
            for s in samples:
                snap = self.fred.as_of_sampled(spec.sid, s, start)
                if snap and o in snap:
                    found = (s, snap)
                    break
            first = transform(found[1], o, spec.kind, spec.scale, freq) if found else None
            out.append(Print(o, found[0] if found else None, first, transform(cur, o, spec.kind, spec.scale, freq), freq))
        return out
