"""Wayback Machine source: historical events (<=2025) without touching
Cloudflare at all — plain requests to web.archive.org.

Flow per event: CDX query finds the newest 200 capture of each candidate URL,
then /web/<ts>id_/ returns the ORIGINAL bytes (no wayback wrapper).
"""
from __future__ import annotations

import gzip
import re
import json
import random
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
    time.sleep(random.uniform(2.5, 4.0))


def cdx_newest(url: str, limit: int = 3) -> str | None:
    """Newest timestamp of a 200 capture for url, or None. CDX is rate-limited
    from datacenter IPs — treat as best-effort fallback only."""
    for attempt in range(3):
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
            if r.status_code in (429, 503):
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                return None
            rows = r.json()
            if not isinstance(rows, list) or len(rows) < 2:
                return None
            return rows[-1][1]  # last row = newest
        except Exception:
            time.sleep(3)
    return None


NOW_TS = "20261101000000"


def wayback_get(url: str, ts: str = NOW_TS, log=None) -> bytes | None:
    """Fetch original bytes. Direct now-timestamp fetch redirects to the
    closest-to-now capture (= latest); one request, no CDX needed.
    Retries with backoff on wayback's aggressive 429/503 rate limits."""
    for attempt in range(4):
        try:
            r = _s().get(f"{WEB}/{ts}id_/{url}", timeout=60)
            _sleep()
            if r.status_code in (429, 503):
                wait = 8 * (attempt + 1) + random.uniform(0, 4)
                if log:
                    log(f"HTTP {r.status_code} (rate limited), backoff {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                if log:
                    log(f"HTTP {r.status_code}: {url}")
                return None
            body = r.content
            if body[:2] == b"\x1f\x8b":  # gzip'd original bytes
                body = gzip.decompress(body)
            return body if len(body) > 200 else None
        except Exception as e:
            if log:
                log(f"fetch error {e!r}")
            time.sleep(5)
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
    """Static page URL variants for a legacy event. JSON-era schedule shells
    are excluded — their content arrives via XHR, useless as static HTML."""
    region, year = event["region"], event["year"]
    yy = str(year)[2:]
    if year < 2013:
        return list(event.get("urls", []))  # curated pre-2013 paths
    return [
        f"https://www.blackhat.com/{region}-{yy}/briefings.html",
        f"https://www.blackhat.com/{region}-{yy}/archives.html",
    ]


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
        body = wayback_get(url, log=say)  # direct now-ts fetch (latest capture)
        if not body:
            ts = cdx_newest(url)
            if ts:
                body = wayback_get(url, ts, log=say)
        if not body:
            say(f"no capture: {url}")
            continue
        say(f"got {len(body)}B via web.archive.org: {url}")
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
        body = wayback_get(url, log=say)
        if not body:
            ts = cdx_newest(url)
            if ts:
                body = wayback_get(url, ts, log=say)
        if not body:
            say(f"no capture: {url}")
            continue
        html = body.decode("utf-8", "replace")
        say(f"got {len(html)}B page via web.archive.org: {url} (pdfs: {html.lower().count('.pdf')})")
        if ".pdf" in html.lower():
            return {
                "status": "ok",
                "kind": "legacy",
                "region": event["region"],
                "year": year,
                "html": html,
                "meta": {"source": "wayback", "url": url, "kind": "legacy",
                         "title": f"wayback {ts}", "trace": trace},
            }
        # 2013-2014 era: listing pages link per-talk detail pages instead of
        # direct PDFs ("us-15-Gaddam-Securing-Your-Big-Data.html"). Derive
        # speaker+title from the slug — zero extra requests.
        detail = _records_from_detail_links(html, event["region"], year)
        if detail:
            say(f"{len(detail)} talks from detail-page links")
            return {
                "status": "ok",
                "kind": "records",
                "region": event["region"],
                "year": year,
                "records": detail,
                "meta": {"source": "wayback", "url": url, "kind": "records",
                         "title": f"wayback {ts}", "trace": trace},
            }
    say("no usable wayback capture")
    return {"status": "failed", "region": event["region"], "year": year,
            "meta": {"source": "wayback", "trace": trace}}


def _records_from_detail_links(html: str, region: str, year: int) -> list[dict]:
    """Listing pages of the 2013-2015 era link root-level talk pages whose
    slugs carry speaker+title: <region>-<yy>-<Author>-<Title>.html"""
    yy = str(year)[2:]
    prefix = f"{region}-{yy}-"
    slugs = re.findall(
        rf'href="(?:https?://www\.blackhat\.com)?/({re.escape(prefix)}[^"/]+?)\.html"',
        html,
    )
    label = f"{region.upper()}-{yy}" if region != "asia" else f"Asia-{yy}"
    records = []
    seen: set[str] = set()
    for slug in dict.fromkeys(slugs):
        parts = slug[len(prefix):].split("-")
        if not parts or not parts[0]:
            continue
        speaker = parts[0] if len(parts) > 1 else ""
        title = " ".join(parts[1:]) if len(parts) > 1 else parts[0]
        if len(title) < 4:
            continue
        key = slug.lower()
        if key in seen:
            continue
        seen.add(key)
        rid = f"{region}{yy}-" + re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:60]
        records.append(
            {
                "id": rid,
                "event": {"region": region, "year": year, "label": label},
                "title": title,
                "speakers": ([{"name": speaker, "company": None, "role": None}]
                             if 2 < len(speaker) < 25 else []),
                "abstract": "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": f"https://web.archive.org/web/2/https://www.blackhat.com/{slug}.html",
            }
        )
    return records


def wayback_inventory() -> str | None:
    """archives.html original bytes via wayback, or None."""
    body = wayback_get(ARCHIVES_ORIGINAL)
    if not body:
        ts = cdx_newest(ARCHIVES_ORIGINAL)
        if ts:
            body = wayback_get(ARCHIVES_ORIGINAL, ts)
    if not body:
        return None
    return body.decode("utf-8", "replace")
