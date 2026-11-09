"""Virus Bulletin conference adapter — virusbulletin.com keeps one archive
page per edition (vb91…vb2026, conference since 1991) behind Cloudflare.
Each /conference/vb<YYYY>/programme/ page lists talks as
abstracts/<slug> links with speaker (+affiliation) as trailing text —
the same walk-between-anchors shape as the Black Hat us-13 day pages."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

ID = "vb"
NAME = "Virus Bulletin"
URL = "https://www.virusbulletin.com/conference/"
DESCRIPTION = "Virus Bulletin Conference, since 1991 — the anti-malware industry's longest-running technical conference."
BASE = "https://www.virusbulletin.com/conference"
FIRST_YEAR = 2002  # 1991-2001 exist only as PDF conference reports, no programme pages
LAST_YEAR = 2026  # vb2027 is future


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


_NOISE_LABELS = {
    "keynote address", "opening address", "closing address", "panel",
    "break", "lunch", "coffee", "registration", "welcome", "q&a",
    "vb quiz", "party", "reception",
}


def _speaker_from_block(a, title: str) -> dict | None:
    """Speaker text trails the title inside the anchor's enclosing block
    (li/p/div). Strip schedule noise (times, weekdays, room labels), lift a
    parenthesised affiliation into company, and take the first name-like
    chunk."""
    block = a.find_parent(["li", "p", "div", "td", "h3", "h4"])
    if block is None:
        return None
    tail = block.get_text(" ", strip=True).replace(title, " ", 1)
    tail = re.sub(r"\d{1,2}[:.]\d{2}", " ", tail)
    tail = re.sub(
        r"\b\d{1,2}(st|nd|rd|th)?\s+"
        r"(january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\b", " ", tail, flags=re.I)
    tail = re.sub(r"\b(mon|tues|wednes|thurs|fri|satur|sun)day\b", " ", tail, flags=re.I)
    tail = re.sub(r"\b(red|green|blue|purple|small|main)\s+room\b", " ", tail, flags=re.I)
    tail = re.sub(r"\bstream\b", " ", tail, flags=re.I)
    company = None
    m = re.search(r"\(([^)]{2,40})\)", tail)
    if m:
        company = m.group(1)
        tail = (tail[: m.start()] + tail[m.end():]).strip(" ,")
    for chunk in re.split(r"[;\u2022\u00b7]|,|\s{2,}", tail):
        chunk = re.sub(r"\s+", " ", chunk).strip(" .–-|")
        if not (2 < len(chunk) < 45) or re.search(r"\d", chunk):
            continue
        if chunk.lower() in _NOISE_LABELS or len(chunk.split()) > 5:
            continue
        return {"name": chunk, "company": company, "role": None}
    return None


def parse_programme(year: int, html: str) -> list[dict]:
    """Talks = anchors into abstracts/<slug>; the speaker trails the title
    inside the same block element."""
    if "/abstracts/" not in html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    anchors = [
        a for a in soup.select('a[href*="/abstracts/"]')
        if len(a.get_text(" ", strip=True)) >= 8
    ]
    records: list[dict] = []
    seen: set[str] = set()
    for a in anchors:
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        key = _slug(title)
        if not key or key in seen:
            continue
        seen.add(key)
        sp = _speaker_from_block(a, title)
        records.append(
            {
                "id": f"vb{year % 100:02d}-{key}",
                "event": {"region": "eu", "year": year, "label": f"VB{year}"},
                "title": title,
                "speakers": [sp] if sp else [],
                "abstract": "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": f"{BASE}/vb{year % 100 if year < 2000 else year}/programme/",
            }
        )
    return records


def collect(ctx: dict) -> dict[str, dict]:
    from crawler.capture import _new_page, clear_challenge
    from crawler.dataset import atomic_write_json

    cache_dir = Path(ctx["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, dict] = dict(ctx["cache_read"])
    if ctx["use_cache"]:
        return captures

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = [
        y for y in range(FIRST_YEAR, LAST_YEAR + 1)
        if (wanted is None or f"vb-{y}" in wanted)
        and not (captures.get(f"vb-{y}", {}).get("status") == "ok" and not ctx["refresh"])
    ]
    print(f"[vb] to crawl: {len(todo)} editions")

    if not todo:
        return captures

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser, _ctx, page = _new_page(pw)
        try:
            for i, year in enumerate(todo):
                key = f"vb-{year}"
                # 1991-1999 editions use two-digit paths (vb95), 2000+ four
                tag = year % 100 if year < 2000 else year
                url = f"{BASE}/vb{tag}/programme/"
                trace: list[str] = []
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    ok = clear_challenge(page, url, log=lambda s: trace.append(s))
                    title = page.title()
                    trace.append(f"title='{title}'")
                    html = page.content() if ok else ""
                    recs = parse_programme(year, html) if html else []
                    trace.append(f"programme {len(html)}B -> {len(recs)} talks")
                    cap = {
                        "status": "ok" if recs else "failed",
                        "kind": "records",
                        "records": recs,
                        "meta": {"source": url, "url": url, "kind": "records",
                                 "title": title, "trace": trace},
                    }
                except Exception as e:
                    trace.append(f"exception: {e!r}")
                    cap = {"status": "failed", "kind": "records", "records": [],
                           "meta": {"source": url, "url": url, "trace": trace}}
                atomic_write_json(cache_dir / f"{key}.json", cap)
                captures[key] = cap
                print(f"    [{i + 1}/{len(todo)}] {key}: "
                      f"{'ok' if cap['status'] == 'ok' else 'FAILED'} ({len(cap['records'])} talks)")
                if i + 1 < len(todo):
                    time.sleep(20 + (year % 10))  # stay under Cloudflare's radar
        finally:
            browser.close()
    return captures
