"""USENIX Security adapter — usenix.org technical-sessions listings.

The listing page embeds every paper as article.node-paper with h2 title link
and a people line ("Name and Name, Affiliation; ..."). Abstracts and PDFs
live on per-presentation pages — future enrichment; listing gives title,
speakers, source link for the whole year in ONE request.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.net import curl_get

ID = "usenix"
NAME = "USENIX Security"
BASE = "https://www.usenix.org"
YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_people(text: str) -> list[dict]:
    """"Cassidy Gibson and Daniel Olszewski, University of Florida; Name, MIT"
    -> [{name, company}, ...] (names within a block share the affiliation)."""
    speakers = []
    for block in re.split(r"[;·]|·", text):
        block = block.strip(" ,;")
        if not block:
            continue
        if "," in block:
            names_part, _, affil = block.rpartition(",")
            affil = affil.strip()
        else:
            names_part, affil = block, ""
        for name in re.split(r"\s+and\s+|,", names_part):
            name = name.strip()
            if 2 < len(name) < 60 and not re.search(r"\d|University|Lab|Inc|Corp|Institute", name):
                speakers.append({"name": name, "company": affil or None, "role": None})
    return speakers[:8]


def collect_year(year: int, log=None) -> dict:
    say = log or (lambda s: None)
    url = f"{BASE}/conference/usenixsecurity{str(year)[2:]}/technical-sessions"
    code = 0
    html = ""
    for attempt in range(3):
        code, html = curl_get(url, timeout=60)
        time.sleep(1.5)
        if code == 404:
            return {"status": "skipped", "meta": {"trace": [f"no page for {year}"]}}
        if code == 200 and html:
            break
        time.sleep(10 * (attempt + 1))
    else:
        return {"status": "failed", "meta": {"trace": [f"HTTP {code} for {year}"]}}

    soup = BeautifulSoup(html, "lxml")
    records = []
    seen: set[str] = set()
    for art in soup.select("article.node-paper"):
        h2 = art.find("h2")
        if not h2:
            continue
        a = h2.find("a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        people = art.find(class_="field-name-field-paper-people-text")
        speakers = parse_people(people.get_text(" ", strip=True)) if people else []
        records.append(
            {
                "id": f"ux{str(year)[2:]}-{_slug(title)}",
                "event": {"region": "us", "year": year, "label": f"USENIX {str(year)[2:]}"},
                "title": title,
                "speakers": speakers,
                "abstract": "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": href if href.startswith("http") else BASE + href,
            }
        )
    say(f"{year}: {len(records)} papers")
    if not records:
        return {"status": "failed", "meta": {"trace": [f"{year}: no papers parsed"]}}
    return {
        "status": "ok",
        "kind": "records",
        "records": records,
        "meta": {"source": BASE, "url": url, "title": f"USENIX Security {year}", "trace": []},
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
        key = f"usenix-{year}"
        if wanted and key not in wanted and str(year) not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, year))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    say(f"to crawl: {len(todo)} year(s)")

    for i, (key, year) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] usenix/{key}")
        cap = collect_year(year, log=say)
        (cache_dir / f"{key}.json").write_text(
            json.dumps(cap, ensure_ascii=False), encoding="utf-8"
        )
        captures[key] = cap
        if cap.get("status") == "ok":
            print(f"    ok: {len(cap['records'])} papers")
        elif cap.get("status") == "skipped":
            print("    skipped (no page)")
        else:
            print("    FAILED")
    return captures
