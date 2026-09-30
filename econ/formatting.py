"""Number formatting and beat/miss logic shared by the PDF and the website.

Moved unchanged from the original build.py so both outputs keep formatting identically.
"""

MINUS = "−"


def is_range(v):
    return isinstance(v, dict)


def has_range(d):
    """True if any consensus in the edition is a published range."""
    return any(is_range(r[k]["cons"]) for sec in d["sections"] for r in sec["rows"] for k in ("p1", "p2"))


def fmt(v, kind):
    """Format a figure for display. None -> "—" (no public consensus / no data).

    A consensus may also be a published forecast range {"lo": x, "hi": y} -> "3.2–3.5%".
    """
    if v is None:
        return "—"
    if is_range(v):
        lo, hi = fmt(v["lo"], kind), fmt(v["hi"], kind)
        if lo.endswith("%") and hi.endswith("%"):
            lo = lo[:-1]
        sep = " to " if v["hi"] < 0 else "\u2013"   # "−39 to −7" reads better than "−39–−7"
        return f"{lo}{sep}{hi}"
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
    """'beat' / 'miss' / '' for one release, given the row's `better` direction."""
    c, a, b = p["cons"], p["act"], row["better"]
    if c is None or a is None or b == "none":
        return ""
    if is_range(c):
        # Against a published range: only an actual outside the range is a beat or a miss.
        if c["lo"] <= a <= c["hi"]:
            return ""
        above = a > c["hi"]
    else:
        if a == c:
            return ""
        above = a > c
    good = above if b == "higher" else not above
    return "beat" if good else "miss"


def bp_change(a, b):
    """Yield change from a to b in basis points, e.g. '+78 bp'."""
    return f'{"+" if b >= a else MINUS}{abs(b - a) * 100:.0f} bp'


# ---------- market sentiment ----------
def mood_of(a):
    """AAII reading -> the mood with the largest share: Bullish / Neutral / Bearish (Mixed on a tie)."""
    shares = {"Bullish": a["bull"], "Neutral": a["neutral"], "Bearish": a["bear"]}
    top = max(shares.values())
    leaders = [k for k, v in shares.items() if v == top]
    label = leaders[0] if len(leaders) == 1 else "Mixed"
    return {"label": label, "cls": {"Bullish": "beat", "Bearish": "miss"}.get(label, "")}


def spread(bull, bear):
    """Bull-bear spread in percentage points, e.g. '+4.2 pts'."""
    if bull is None or bear is None:
        return "—"
    x = bull - bear
    return f'{"+" if x >= 0 else MINUS}{abs(x):.1f} pts'


def fg_class(v):
    """CNN Fear & Greed zones: 0–44 fear (rust), 45–55 neutral, 56–100 greed (green)."""
    return "miss" if v < 45 else "beat" if v > 55 else ""
