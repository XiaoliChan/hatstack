"""KCon adapter (知道创宇 KCon 黑客江湖) — root 404s but history.html links
per-year pages (kcon2021..2024.html) whose .title divs hold "议题 · 讲者"."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.net import curl_get

ID = "kcon"
NAME = "KCon"
URL = "https://kcon.knownsec.com/history.html"
DESCRIPTION = "Knownsec's KCon hacker conference in China, since 2012."
HISTORY = "https://kcon.knownsec.com/history.html"
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_year_page(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for el in soup.select(".title, .item .name, h3"):
        text = el.get_text(" ", strip=True)
        if not text or _TIME_RE.match(text) or len(text) < 6:
            continue
        if any(k in text for k in ("茶歇", "抽奖", "开幕", "颁奖", "午休")):
            continue
        if "·" in text:
            title, _, speaker = text.rpartition("·")
            title = title.strip()
            speaker = speaker.strip()
        else:
            title, speaker = text.strip(), ""
        if not title or _TIME_RE.match(title):
            continue
        records.append(
            {
                "id": f"kcon{str(year)[2:]}-{_slug(title)[:50]}",
                "event": {"region": "asia", "year": year, "label": f"KCon {str(year)[2:]}"},
                "title": title,
                "speakers": (
                    [{"name": s.strip(), "company": None, "role": None}
                     for s in re.split(r"[、,，]", speaker) if 1 <= len(s.strip()) <= 20]
                )[:4],
                "abstract": "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": f"https://kcon.knownsec.com/kcon{year}.html",
            }
        )
    seen = set()
    out = []
    for r in records:
        if r["title"] in seen:
            continue
        seen.add(r["title"])
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

    code, html = curl_get(HISTORY, timeout=30)
    time.sleep(1.0)
    if code != 200:
        cap = {"status": "failed", "meta": {"trace": [f"history.html HTTP {code}"]}}
        atomic_write_json(cache_dir / "all.json", cap)
        captures["all"] = cap
        return captures
    years = sorted({int(y) for y in re.findall(r'href="kcon(\d{4})\.html"', html)}, reverse=True)
    print(f"    history.html: editions {years}")

    all_records = []
    for year in years:
        code, yhtml = curl_get(f"https://kcon.knownsec.com/kcon{year}.html", timeout=30)
        time.sleep(1.0)
        if code != 200:
            print(f"    kcon{year}: HTTP {code}")
            continue
        recs = parse_year_page(yhtml, year)
        print(f"    kcon{year}: {len(recs)} talks")
        all_records.extend(recs)

    cap = {
        "status": "ok" if all_records else "failed",
        "kind": "records",
        "records": all_records,
        "meta": {"source": URL, "url": URL, "title": "KCon",
                 "trace": [f"{len(years)} editions, {len(all_records)} talks total"]},
    }
    atomic_write_json(cache_dir / "all.json", cap)
    captures["all"] = cap
    print(f"    KCon total: {len(all_records)} talks")
    return captures
