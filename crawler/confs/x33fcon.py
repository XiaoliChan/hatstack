"""x33fcon adapter — x33fcon.com is a single-page JS app whose archive
renders client-side. We render the homepage once and parse talk blocks
(headings + speaker/pdf links) from the rendered DOM."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.dataset import atomic_write_json
from crawler.render import rendered_html

ID = "x33fcon"
NAME = "x33fcon"
DESCRIPTION = "Polish conference for red teamers and exploit developers."
URL = "https://x33fcon.com/"
BASE = "https://x33fcon.com/"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_rendered(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    # talk blocks: cards with a heading and a pdf/youtube link
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
            continue  # not a talk block
        # year from nearby edition text or pdf path
        year_m = re.search(r"(20[12]\d)", str(block)[:500] or "")
        year = int(year_m.group(1)) if year_m else 0
        records.append(
            {
                "id": f"x33f-{_slug(title)}",
                "event": {"region": "eu", "year": year, "label": "x33fcon"},
                "title": title,
                "speakers": [],
                "abstract": block.get_text(" ", strip=True)[:400],
                "track": None,
                "files": {
                    "slides": pdf["href"] if pdf else None,
                    "whitepaper": None,
                    "tool": None,
                },
                "video_url": yt["href"] if yt else None,
                "source_url": BASE,
            }
        )
    # dedupe by title
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

    print("[x33fcon] rendering", BASE)
    with sync_playwright() as pw:
        html = rendered_html(pw, BASE, settle=8.0)
    if not html:
        cap = {"status": "failed", "meta": {"trace": ["render failed"]}}
        captures["all"] = cap
        atomic_write_json(cache_dir / "all.json", cap)
        return captures
    records = parse_rendered(html)
    print(f"    rendered {len(html)}B -> {len(records)} talks")
    cap = {
        "status": "ok" if records else "failed",
        "kind": "records",
        "records": records,
        "meta": {"source": BASE, "url": BASE, "title": "x33fcon",
                 "trace": [f"rendered {len(html)}B, {len(records)} talks",
                           "structure: " + ("rich" if records else "unknown — inspect cache")]},
    }
    atomic_write_json(cache_dir / "all.json", cap)
    (cache_dir / "rendered.html").write_text(html, encoding="utf-8")  # for structure iteration
    captures["all"] = cap
    return captures
