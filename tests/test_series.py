import json
import os
import subprocess
import sys

import pytest

from econ.fred import snapshot
from econ.render import ROOT
from econ.series import (MANUAL, ROWS, period_label, period_to_obs, prev_date,
                         round_half_up, row_keys, transform)

# CPI-like monthly index with the Oct-2025 observation missing (government shutdown).
SNAP = {
    "2024-08-01": 100.0, "2024-09-01": 100.2, "2024-10-01": 100.4, "2024-11-01": 100.6,
    "2025-08-01": 103.0, "2025-09-01": 103.3, "2025-11-01": 103.9,
}


def test_yoy_is_by_date_not_row_offset():
    # 12 rows back from Nov-2025 would not be Nov-2024 because Oct-2025 is missing.
    assert round(transform(SNAP, "2025-11-01", "yoy", 1, "M"), 4) == round((103.9 / 100.6 - 1) * 100, 4)


def test_mom_refuses_to_bridge_a_missing_month():
    assert transform(SNAP, "2025-11-01", "mom", 1, "M") is None      # Oct missing -> no silent Sep compare
    assert round(transform(SNAP, "2025-09-01", "mom", 1, "M"), 4) == round((103.3 / 103.0 - 1) * 100, 4)


def test_prev_dates():
    assert prev_date("2026-01-01", "M") == "2025-12-01"
    assert prev_date("2026-04-01", "Q") == "2026-01-01"
    assert prev_date("2026-09-12", "W") == "2026-09-05"


@pytest.mark.parametrize("label, obs", [
    ("Aug", "2026-08-01"), ("Dec", "2025-12-01"), ("Wk 9/12", "2026-09-12"),
    ("9/17", "2026-09-17"), ("Q2", "2026-04-01"), ("Aug (F)", None),
])
def test_period_to_obs(label, obs):
    assert period_to_obs(label, "2026-09-23") == obs


def test_period_labels_round_trip():
    assert period_label("2026-09-12", "W", "week") == "Wk 9/12"
    assert period_label("2026-09-17", "W", "date") == "9/17"
    assert period_label("2026-04-01", "Q", "quarter") == "Q2"
    assert period_label("2026-08-01", "M", "month") == "Aug"


def test_first_print_uses_release_day_snapshot():
    # PAYEMS-style history: Jul first printed 8/7 (then revised 9/4); Jun revised on both dates.
    hist = {
        "2026-06-01": [("2026-07-02", "2026-08-06", 158984.0), ("2026-08-07", "2026-09-03", 158881.0),
                       ("2026-09-04", "9999-12-31", 158892.0)],
        "2026-07-01": [("2026-08-07", "2026-09-03", 158858.0), ("2026-09-04", "9999-12-31", 158913.0)],
    }
    first = transform(snapshot(hist, "2026-08-07"), "2026-07-01", "diff", 1, "M")
    current = transform(snapshot(hist, "9999-12-31"), "2026-07-01", "diff", 1, "M")
    assert round(first) == -23 and round(current) == 21


def test_rounding_is_half_up_and_never_negative_zero():
    assert round_half_up(0.25, 1) == 0.3 and round_half_up(-0.25, 1) == -0.3
    assert str(round_half_up(-0.004, 1)) == "0.0"


def test_every_row_is_either_fred_or_manual():
    d = json.loads((ROOT / "data" / "2026-09-23.json").read_text())
    keys = [k for s in d["sections"] for k, _ in row_keys(s)]
    assert len(keys) == len(set(keys)), "row keys must be unique"
    uncovered = [k for k in keys if k not in ROWS and k not in MANUAL]
    assert uncovered == []
    assert not (set(ROWS) - set(keys)), "ROWS mentions a row that no longer exists"


@pytest.mark.skipif(not os.environ.get("FRED_LIVE"), reason="live FRED check; set FRED_LIVE=1 (uses FRED_API_KEY)")
def test_live_regression_against_verified_edition():
    r = subprocess.run([sys.executable, "fetch_actuals.py", "--check", "data/2026-09-23.json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
