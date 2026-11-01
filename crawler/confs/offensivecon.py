"""OffensiveCon adapter — offensivecon.org static speaker pages.

/speakers/<year>/ holds div.speaker-item blocks: h5 title, p.intro abstract,
speaker anchor links. Years live: 2020, 2022-2025 (older editions 404).
Slides are not published on-site for most years; files stay empty.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.net import curl_get
from crawler.dataset import atomic_write_json

ID = "offensivecon"
NAME = "OffensiveCon"
DESCRIPTION = "Berlin conference focused on offensive security and exploit development, since 2018."
URL = "https://www.offensivecon.org/"
BASE = "https://www.offensivecon.org"
YEARS = [2025, 2024, 2023, 2022, 2020]  # live pages; 2018/2019/2021 404


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def collect_year(year: int, log=None) -> dict:
    say = log or (lambda s: None)
    url = f"{BASE}/speakers/{year}/"
    for attempt in range(2):
        code, html = curl_get(url)
        time.sleep(1.0)
        if code == 404:
            return {"status": "skipped", "meta": {"trace": [f"no page for {year}"]}}
        if code == 200 and html:
            break
        time.sleep(6 * (attempt + 1))
    else:
        return {"status": "failed", "meta": {"trace": [f"HTTP {code} for {year}"]}}

    soup = BeautifulSoup(html, "lxml")
    records = []
    for item in soup.select("div.speaker-item"):
        h5 = item.find("h5")
        if not h5:
            continue
        title = h5.get_text(" ", strip=True)
        title = re.sub(r"\s*-\s*(KEYNOTE|WORKSHOP)\s*$", "", title)
        abstract = item.find("p", class_="intro")
        speakers = []
        seen_names: set[str] = set()
        for a in item.select("a"):
            name = a.get_text(" ", strip=True)
            if re.fullmatch(r"(read more|more|→|.+ →)", name, re.I):
                # the real speaker name lives in the anchor's title attribute
                # ("<a title="Perri Adams">Read more</a>")
                name = (a.get("title") or "").strip()
            if 2 < len(name) < 60 and name.lower() not in seen_names:
                seen_names.add(name.lower())
                speakers.append({"name": name, "company": None, "role": None})
        records.append(
            {
                "id": f"ocon{str(year)[2:]}-{_slug(title)}",
                "event": {"region": "eu", "year": year, "label": f"OCon {str(year)[2:]}"},
                "title": title,
                "speakers": speakers[:6],
                "abstract": abstract.get_text(" ", strip=True)[:4000] if abstract else "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": url,
            }
        )
    say(f"{year}: {len(records)} talks")
    if not records:
        return {"status": "failed", "meta": {"trace": [f"{year}: no speaker-items parsed"]}}
    return {
        "status": "ok",
        "kind": "records",
        "records": records,
        "meta": {"source": BASE, "url": url, "title": f"OffensiveCon {year}", "trace": []},
    }


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

    def say(line: str):
        print(f"    {line}")

    if ctx["use_cache"]:
        return captures

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for year in YEARS:
        key = f"ocon-{year}"
        if wanted and key not in wanted and str(year) not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, year))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    say(f"to crawl: {len(todo)} year(s)")

    for i, (key, year) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] offensivecon/{key}")
        try:
            cap = collect_year(year, log=say)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"    ERROR: {e!r} — continuing")
            cap = {"status": "failed", "meta": {"trace": [f"exception: {e!r}"]}}
        atomic_write_json(cache_dir / f"{key}.json", cap)
        captures[key] = cap
        if cap.get("status") == "ok":
            print(f"    ok: {len(cap['records'])} talks")
        elif cap.get("status") == "skipped":
            print("    skipped (no page)")
        else:
            print("    FAILED")
    return captures
