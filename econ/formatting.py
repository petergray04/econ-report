"""Number formatting and beat/miss logic shared by the PDF and the website.

Moved unchanged from the original build.py so both outputs keep formatting identically.
"""

MINUS = "−"


def fmt(v, kind):
    """Format a figure for display. None -> "—" (no public consensus / no data)."""
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
    """'beat' / 'miss' / '' for one release, given the row's `better` direction."""
    c, a, b = p["cons"], p["act"], row["better"]
    if c is None or a is None or b == "none" or a == c:
        return ""
    good = a > c if b == "higher" else a < c
    return "beat" if good else "miss"


def bp_change(a, b):
    """Yield change from a to b in basis points, e.g. '+78 bp'."""
    return f'{"+" if b >= a else MINUS}{abs(b - a) * 100:.0f} bp'
