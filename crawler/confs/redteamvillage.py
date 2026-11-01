"""Red Team Village adapter — redteamvillage.io (the .org domain is expired
and parked). Astro static site; the schedule page links out to the current
DEF CON schedule rather than embedding talks, so historical material arrives
via the DEF CON adapter's villages directory (track='Red Team Village').
This adapter parses the schedule/events pages best-effort."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.net import curl_get

ID = "redteamvillage"
NAME = "Red Team Village"
URL = "https://redteamvillage.io/"
DESCRIPTION = "DEF CON Red Team Village — red teaming talks and workshops."
PAGES = ["https://redteamvillage.io/schedule/", "https://redteamvillage.io/events/"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_page(html: str, year: int, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select("article, .talk, .schedule-item, li, div.card"):
        h = card.find(["h2", "h3", "h4", "h5"], recursive=False)
        if not h:
            continue
        title = h.get_text(" ", strip=True)
        if len(title) < 6:
            continue
        pdf = card.find("a", href=re.compile(r"\.pdf$", re.I))
        yt = card.find("a", href=re.compile(r"youtube\.com|youtu\.be", re.I))
        if not (pdf or yt):
            continue
        records.append(
            {
                "id": f"rtv-{_slug(title)}",
                "event": {"region": "us", "year": year, "label": "RTV"},
                "title": title,
                "speakers": [],
                "abstract": card.get_text(" ", strip=True)[:300],
                "track": "Red Team Village",
                "files": {"slides": pdf["href"] if pdf else None,
                          "whitepaper": None, "tool": None},
                "video_url": yt["href"] if yt else None,
                "source_url": base,
            }
        )
    return records


def collect(ctx: dict) -> dict[str, dict]:
    from crawler.dataset import atomic_write_json

    cache_dir = Path(ctx["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, dict] = dict(ctx["cache_read"])
    if not captures:
        for f in sorted(cache_dir.glob("*.json")):
            try:
                captures[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
    if ctx["use_cache"]:
        return captures
    if "all" in captures and captures["all"].get("status") == "ok" and not ctx["refresh"]:
        return captures

    import datetime as _dt

    year = _dt.date.today().year
    records = []
    trace = []
    for url in PAGES:
        code, html = curl_get(url, timeout=30)
        time.sleep(1.0)
        if code != 200:
            trace.append(f"{url}: HTTP {code}")
            continue
        found = parse_page(html, year, url)
        trace.append(f"{url}: {len(html)}B -> {len(found)} talks")
        records.extend(found)

    if not records:
        trace.append("no embedded talks: schedule links to the current DEF CON "
                     "schedule; historical material arrives via defcon villages track")
    cap = {
        "status": "ok" if records else "failed",
        "kind": "records",
        "records": records,
        "meta": {"source": URL, "url": URL, "title": "Red Team Village", "trace": trace},
    }
    atomic_write_json(cache_dir / "all.json", cap)
    captures["all"] = cap
    print(f"    RTV: {trace[-1]}")
    return captures
