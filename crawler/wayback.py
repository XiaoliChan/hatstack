"""Wayback Machine source: historical events (<=2025) without touching
Cloudflare at all — plain requests to web.archive.org.

Flow per event: CDX query finds the newest 200 capture of each candidate URL,
then /web/<ts>id_/ returns the ORIGINAL bytes (no wayback wrapper).
"""
from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import requests

from .events import LONG_REGION

CDX = "https://web.archive.org/cdx/search/cdx"
WEB = "https://web.archive.org/web"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
ARCHIVES_ORIGINAL = "https://www.blackhat.com/html/archives.html"

_session: requests.Session | None = None


def _s() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": UA})
    return _session


def _sleep():
    time.sleep(1.5)


def cdx_newest(url: str, limit: int = 3) -> str | None:
    """Newest timestamp of a 200 capture for url, or None."""
    try:
        r = _s().get(
            CDX,
            params={
                "url": url,
                "output": "json",
                "filter": "statuscode:200",
                "collapse": "digest",
                "limit": f"-{limit}",
            },
            timeout=30,
        )
        _sleep()
        if r.status_code != 200:
            return None
        rows = r.json()
        if not isinstance(rows, list) or len(rows) < 2:
            return None
        return rows[-1][1]  # last row = newest
    except Exception:
        return None


def wayback_get(url: str, ts: str) -> bytes | None:
    try:
        r = _s().get(f"{WEB}/{ts}id_/{url}", timeout=60)
        _sleep()
        if r.status_code != 200:
            return None
        body = r.content
        if body[:2] == b"\x1f\x8b":  # gzip'd original bytes
            body = gzip.decompress(body)
        return body
    except Exception:
        return None


def json_candidates(event: dict) -> list[str]:
    """sessions.json URL variants for a JSON-era event, microsite + archive."""
    region, year = event["region"], event["year"]
    yy, long_r = str(year)[2:], LONG_REGION[region]
    return [
        f"https://www.blackhat.com/{region}-{yy}/briefings/schedule/sessions.json",
        f"https://www.blackhat.com/archive/{long_r}/{year}/briefings/schedule/sessions.json",
    ]


def page_candidates(event: dict) -> list[str]:
    """Static page URL variants for a legacy event."""
    region, year = event["region"], event["year"]
    yy = str(year)[2:]
    urls = []
    if year < 2013:
        urls.extend(event.get("urls", []))  # curated pre-2013 paths
        return urls
    urls = [
        f"https://www.blackhat.com/{region}-{yy}/briefings.html",
        f"https://www.blackhat.com/{region}-{yy}/archives.html",
        f"https://www.blackhat.com/{region}-{yy}/briefings/schedule/index.html",
    ]
    return urls


def wayback_event(event: dict) -> dict:
    """Best-effort wayback capture for one event. JSON era prefers sessions.json."""
    year = event["year"]
    key = f"{event['region']}-{year}"
    json_era = year >= 2018
    trace: list[str] = []

    def say(line: str):
        print(f"    {line}")
        trace.append(line)

    try_orders = json_candidates(event) if json_era else []
    for url in try_orders:
        ts = cdx_newest(url)
        if not ts:
            say(f"cdx miss: {url}")
            continue
        body = wayback_get(url, ts)
        if not body:
            say(f"cdx {ts} fetch failed: {url}")
            continue
        say(f"cdx {ts} {len(body)}B: {url}")
        try:
            data = json.loads(body)
        except Exception as e:
            say(f"json invalid ({e!r}), next candidate")
            continue
        if not isinstance(data, dict) or not data.get("sessions"):
            say("json has no sessions, next candidate")
            continue
        n = len(data.get("sessions") or {})
        say(f"OK json ({n} sessions) from {ts}")
        return {
            "status": "ok",
            "kind": "json",
            "region": event["region"],
            "year": year,
            "data": data,
            "meta": {"source": "wayback", "url": url, "kind": "json",
                     "title": f"wayback {ts}", "trace": trace},
        }
    for url in page_candidates(event):
        ts = cdx_newest(url)
        if not ts:
            say(f"cdx miss: {url}")
            continue
        body = wayback_get(url, ts)
        if not body:
            say(f"cdx {ts} fetch failed: {url}")
            continue
        html = body.decode("utf-8", "replace")
        say(f"cdx {ts} {len(html)}B page: {url} (pdfs: {html.lower().count('.pdf')})")
        if ".pdf" not in html.lower():
            continue
        return {
            "status": "ok",
            "kind": "legacy",
            "region": event["region"],
            "year": year,
            "html": html,
            "meta": {"source": "wayback", "url": url, "kind": "legacy",
                     "title": f"wayback {ts}", "trace": trace},
        }
    say("no usable wayback capture")
    return {"status": "failed", "region": event["region"], "year": year,
            "meta": {"source": "wayback", "trace": trace}}


def wayback_inventory() -> str | None:
    """archives.html original bytes via wayback, or None."""
    ts = cdx_newest(ARCHIVES_ORIGINAL)
    if not ts:
        return None
    body = wayback_get(ARCHIVES_ORIGINAL, ts)
    if not body:
        return None
    return body.decode("utf-8", "replace")
