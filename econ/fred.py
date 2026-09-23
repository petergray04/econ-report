"""Polite FRED/ALFRED client: first-print (release-day) values and current values.

Rate limiting (FRED answers bursts with HTTP 503/429):
  * one process-wide gate: at most MAX_CONCURRENCY requests in flight and a minimum spacing
    between request starts (FRED's documented API limit is 120 requests/minute);
  * retries with exponential backoff + jitter on 429/5xx/timeouts, honoring Retry-After;
  * on-disk cache in .cache/fred/ — responses for a fixed past vintage never change, so they are
    kept forever; "latest" responses expire after CURRENT_TTL.

With FRED_API_KEY set (recommended) one request per series returns every vintage of every
observation (ALFRED real-time periods), so a first print is exact: the value on the first day
it existed. Without a key we fall back to the public ALFRED CSV sampled at weekly vintage
dates, which is slower and can only pin the release to within a week.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "fred"
API = "https://api.stlouisfed.org/fred"
MAX_CONCURRENCY = 3
MIN_SPACING = 0.55          # seconds between request starts (~109/min, under FRED's 120/min)
CURRENT_TTL = 6 * 3600      # seconds a "latest data" response stays cached
RETRY_STATUS = {429, 500, 502, 503, 504}


class FredError(RuntimeError):
    pass


def load_dotenv(path=ROOT / ".env"):
    """Minimal .env loader so `FRED_API_KEY=...` in a local, git-ignored .env just works."""
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Fred:
    def __init__(self, api_key=None, cache=True, tries=6, verbose=False):
        load_dotenv()
        self.key = api_key if api_key is not None else os.environ.get("FRED_API_KEY") or None
        self.cache = cache
        self.tries = tries
        self.verbose = verbose
        self._sem = threading.BoundedSemaphore(MAX_CONCURRENCY)
        self._lock = threading.Lock()
        self._next_start = 0.0
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0}

    # ---------- transport ----------
    def _wait_turn(self):
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start)
            self._next_start = start + MIN_SPACING
        if start > now:
            time.sleep(start - now)

    def _cache_path(self, url):
        clean = url.replace(self.key, "KEY") if self.key else url
        return CACHE_DIR / (hashlib.sha256(clean.encode()).hexdigest()[:32] + ".txt")

    def get_text(self, url, immutable=False):
        path = self._cache_path(url)
        if self.cache and path.exists():
            age = time.time() - path.stat().st_mtime
            if immutable or age < CURRENT_TTL:
                self.stats["cache_hits"] += 1
                return path.read_text()
        req = urllib.request.Request(url, headers={"User-Agent": "econ-report/1.0 (+https://github.com/petergray04/econ-report)"})
        delay = 2.0
        for attempt in range(1, self.tries + 1):
            with self._sem:
                self._wait_turn()
                self.stats["requests"] += 1
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        text = r.read().decode()
                    break
                except urllib.error.HTTPError as e:
                    if e.code not in RETRY_STATUS or attempt == self.tries:
                        body = e.read().decode(errors="replace")[:300]
                        raise FredError(f"HTTP {e.code} for {self._redact(url)}: {body}") from None
                    wait = float(e.headers.get("Retry-After") or delay)
                except (urllib.error.URLError, TimeoutError) as e:
                    if attempt == self.tries:
                        raise FredError(f"{e} for {self._redact(url)}") from None
                    wait = delay
            self.stats["retries"] += 1
            wait = wait * (0.8 + 0.4 * random.random())
            if self.verbose:
                print(f"  retry {attempt}/{self.tries - 1} in {wait:.1f}s: {self._redact(url)}")
            time.sleep(wait)
            delay = min(delay * 2, 60)
        if self.cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return text

    def _redact(self, url):
        return url.replace(self.key, "***") if self.key else url

    def _api(self, endpoint, immutable=False, **params):
        params.update(api_key=self.key, file_type="json")
        url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
        return json.loads(self.get_text(url, immutable=immutable))

    # ---------- data ----------
    def current(self, sid, start):
        """{date: value} as FRED shows it today (latest vintage)."""
        if self.key:
            j = self._api("series/observations", series_id=sid, observation_start=start)
            return {o["date"]: float(o["value"]) for o in j["observations"] if o["value"] not in ("", ".")}
        return self._csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}")

    def vintages(self, sid, start):
        """History of every observation since `start`: {date: [(realtime_start, realtime_end, value)]}.

        Needs an API key. realtime_start of an observation's earliest period is the day it was first
        published — i.e. its release day — as long as that is after `start`.
        """
        if not self.key:
            raise FredError("vintages() needs FRED_API_KEY")
        j = self._api("series/observations", series_id=sid, observation_start=start,
                      realtime_start=start, realtime_end="9999-12-31")
        hist = {}
        for o in j["observations"]:
            v = None if o["value"] in ("", ".") else float(o["value"])
            hist.setdefault(o["date"], []).append((o["realtime_start"], o["realtime_end"], v))
        for periods in hist.values():
            periods.sort()
        return hist

    def as_of_sampled(self, sid, vintage, start):
        """No-key fallback: the series as it looked on `vintage` (ALFRED public CSV)."""
        url = (f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}"
               f"&vintage_date={vintage}&cosd={start}")
        immutable = dt.date.fromisoformat(vintage) < dt.date.today()
        try:
            return self._csv(url, immutable=immutable)
        except FredError as e:
            if "HTTP 404" in str(e) or "HTTP 400" in str(e):
                return None
            raise

    def _csv(self, url, immutable=False):
        rows = list(csv.reader(io.StringIO(self.get_text(url, immutable=immutable))))[1:]
        return {r[0]: float(r[1]) for r in rows if len(r) > 1 and r[1] not in ("", ".")}


def snapshot(hist, vintage):
    """Series values as they stood on `vintage` (YYYY-MM-DD), from a vintages() history."""
    out = {}
    for date, periods in hist.items():
        for rs, re_, v in periods:
            if rs <= vintage <= re_ and v is not None:
                out[date] = v
                break
    return out
