"""KCon adapter (知道创宇黑客江湖) — kcon.knownsec.com is a 1.3KB JS shell.
Render-first adapter: renders the site, dumps rendered.html to the cache, and
best-effort parses talk blocks (headings + speaker/pdf links). The dump lets
the parser be sharpened on real structure next iteration."""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.dataset import atomic_write_json
from crawler.render import rendered_html

ID = "kcon"
NAME = "KCon"
URLS = ["https://kcon.knownsec.com/", "https://kcon.knownsec.com/agenda"]


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
        if len(title) < 6:
            continue
        pdf = block.find("a", href=re.compile(r"\.pdf$", re.I))
        if not pdf:
            continue
        text = block.get_text(" ", strip=True)
        year_m = re.search(r"(20[12]\d)", text[:200])
        year = int(year_m.group(1)) if year_m else 0
        records.append(
            {
                "id": f"kcon-{_slug(title)}",
                "event": {"region": "asia", "year": year, "label": "KCon"},
                "title": title,
                "speakers": [],
                "abstract": text[:400],
                "track": None,
                "files": {"slides": pdf["href"], "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": URLS[0],
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
            print(f"[kcon] rendering {url}")
            html = rendered_html(pw, url, settle=8.0)
            if not html:
                best["meta"]["trace"].append(f"render failed: {url}")
                continue
            records = parse_rendered(html)
            best["meta"]["trace"].append(f"{url}: {len(html)}B -> {len(records)} talks")
            (cache_dir / "rendered.html").write_text(html, encoding="utf-8")
            if records:
                best = {
                    "status": "ok",
                    "kind": "records",
                    "records": records,
                    "meta": {"source": url, "url": url, "title": "KCon",
                             "trace": best["meta"]["trace"]},
                }
                break
    print(f"    {best['meta'].get('trace', [])[-1]}")
    atomic_write_json(cache_dir / "all.json", best)
    captures["all"] = best
    return captures
