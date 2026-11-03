"""Nullcon adapter — nullcon.net/archives is a JS app; render it and parse
talk blocks (headings + slide/pdf links) best-effort, dumping rendered.html
for parser sharpening."""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.render import rendered_html

ID = "nullcon"
NAME = "Nullcon"
URL = "https://nullcon.net/"
DESCRIPTION = "Nullcon — offensive security conference in Goa/Dubai, since 2010."
PAGES = ["https://nullcon.net/archives", "https://nullcon.net/archive"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_rendered(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    year = 0
    for el in soup.select("h1, h2, h3, h4, section, article, li, div.card"):
        h = el if el.name in ("h1", "h2", "h3", "h4") else el.find(["h2", "h3", "h4", "h5"], recursive=False)
        if not h:
            continue
        title = h.get_text(" ", strip=True)
        if not title or len(title) < 6:
            continue
        ym = re.search(r"(20[12]\d)", (el.get_text(" ", strip=True))[:120])
        if ym:
            year = int(ym.group(1))
        pdf = el.find("a", href=re.compile(r"\.pdf$", re.I))
        deck = el.find("a", href=re.compile(r"speakerdeck|slideshare|docs\.google", re.I))
        yt = el.find("a", href=re.compile(r"youtube\.com|youtu\.be", re.I))
        if not (pdf or deck or yt):
            continue
        text = el.get_text(" ", strip=True)
        speakers = [
            {"name": s.strip(), "company": None, "role": None}
            for s in re.split(r"\s{2,}|·|,", text[len(title):len(title)+200])
            if 3 < len(s.strip()) < 40 and not re.search(r"\d", s)
        ][:4]
        records.append({
            "id": f"nullcon-{_slug(title)}",
            "event": {"region": "asia", "year": year or 0, "label": "Nullcon"},
            "title": title,
            "speakers": speakers,
            "abstract": "",
            "track": None,
            "files": {"slides": pdf["href"] if pdf else None,
                      "whitepaper": None, "tool": None},
            "video_url": yt["href"] if yt else None,
            "source_url": PAGES[0],
        })
    seen = set()
    out = []
    for r in records:
        k = r["title"].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


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

    from playwright.sync_api import sync_playwright

    best = {"status": "failed", "meta": {"trace": []}}
    with sync_playwright() as pw:
        for url in PAGES:
            print(f"[nullcon] rendering {url}")
            html = rendered_html(pw, url, settle=9.0)
            if not html:
                best["meta"]["trace"].append(f"render failed: {url}")
                continue
            records = parse_rendered(html)
            best["meta"]["trace"].append(f"{url}: {len(html)}B -> {len(records)} talks")
            (cache_dir / "rendered.html").write_text(html, encoding="utf-8")
            if records:
                best = {"status": "ok", "kind": "records", "records": records,
                        "meta": {"source": url, "url": url, "title": "Nullcon",
                                 "trace": best["meta"]["trace"]}}
                break
    print(f"    nullcon: {best['meta'].get('trace', [])[-1]}")
    atomic_write_json(cache_dir / "all.json", best)
    captures["all"] = best
    return captures
