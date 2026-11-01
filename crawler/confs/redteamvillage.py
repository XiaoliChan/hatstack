"""Red Team Village adapter — redteamvillage.org is an SPA (all routes return
the same JS shell). Render the homepage/talks route once, parse talk blocks,
and dump rendered.html into the cache so the parser can be sharpened on real
structure next iteration."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.dataset import atomic_write_json
from crawler.render import rendered_html

ID = "redteamvillage"
NAME = "Red Team Village"
URLS = ["https://redteamvillage.org/", "https://redteamvillage.org/talks/"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_rendered(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for block in soup.select("div, section, article, li"):
        h = block.find(["h2", "h3", "h4", "h5"], recursive=False)
        if not h:
            continue
        title = h.get_text(" ", strip=True)
        if len(title) < 8:
            continue
        pdf = block.find("a", href=re.compile(r"\.pdf$", re.I))
        yt = block.find("a", href=re.compile(r"youtube\.com|youtu\.be", re.I))
        if not (pdf or yt):
            continue
        year_m = re.search(r"(20[12]\d)", block.get_text(" ", strip=True)[:200])
        year = int(year_m.group(1)) if year_m else 0
        text = block.get_text(" ", strip=True)
        records.append(
            {
                "id": f"rtv-{_slug(title)}",
                "event": {"region": "us", "year": year, "label": "RTV"},
                "title": title,
                "speakers": [],
                "abstract": text[:400],
                "track": "Red Team Village",
                "files": {
                    "slides": pdf["href"] if pdf else None,
                    "whitepaper": None,
                    "tool": None,
                },
                "video_url": yt["href"] if yt else None,
                "source_url": URLS[1],
            }
        )
    seen = set()
    out = []
    for r in records:
        if r["title"].lower() in seen:
            continue
        seen.add(r["title"].lower())
        out.append(r)
    return out


def collect(ctx: dict) -> dict[str, dict]:
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
    if captures.get("all", {}).get("status") == "ok" and not ctx["refresh"]:
        return captures

    from playwright.sync_api import sync_playwright

    best = {"status": "failed", "meta": {"trace": []}}
    with sync_playwright() as pw:
        for url in URLS:
            print(f"[redteamvillage] rendering {url}")
            html = rendered_html(pw, url, settle=8.0)
            if not html:
                best["meta"]["trace"].append(f"render failed: {url}")
                continue
            records = parse_rendered(html)
            best["meta"]["trace"].append(f"{url}: {len(html)}B -> {len(records)} talks")
            if records:
                best = {
                    "status": "ok",
                    "kind": "records",
                    "records": records,
                    "meta": {"source": url, "url": url, "title": "Red Team Village",
                             "trace": best["meta"]["trace"]},
                }
                (cache_dir / "rendered.html").write_text(html, encoding="utf-8")
                break
            (cache_dir / f"rendered-{URLS.index(url)}.html").write_text(
                html, encoding="utf-8"
            )
    print(f"    {best['meta'].get('trace', [])[-1]}")
    atomic_write_json(cache_dir / "all.json", best)
    captures["all"] = best
    return captures
