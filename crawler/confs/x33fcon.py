"""x33fcon adapter — the site is an MDwiki whose content pages are static
markdown files. Archives live at archive/<year>/con.md with agenda tables:
| time | **Speaker** | [Title](s/X.md) | [slides](/slides/*.pdf) |"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from crawler.net import curl_get

ID = "x33fcon"
NAME = "x33fcon"
URL = "https://x33fcon.com/"
DESCRIPTION = "Polish conference where blue and red teams meet, since 2017."
YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017]

_ROW_SKIP = re.compile(r"coffee|lunch|break|opening|closing|registration|party|ctf", re.I)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_agenda_md(md: str, year: int) -> list[dict]:
    records = []
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        speaker_m = re.search(r"\*\*([^*]+)\*\*", line)
        title_m = re.search(r"\[([^\]!][^\]]*)\]\((?!/img)[^)]+\)", line)
        slides_m = re.search(r"\((/slides/[^)]+\.pdf)\)", line)
        if not (speaker_m and title_m):
            continue
        title = title_m.group(1).strip().strip("*").strip()
        title = re.sub(r"^Keynote:\s*", "", title)
        if not title or _ROW_SKIP.fullmatch(title.replace(" ", "")):
            continue
        speakers = [
            {"name": s.strip(), "company": None, "role": None}
            for s in re.split(r"\s+and\s+|,", speaker_m.group(1))
            if 2 <= len(s.strip()) < 40
        ]
        records.append(
            {
                "id": f"x33f{str(year)[2:]}-{_slug(title)}",
                "event": {"region": "eu", "year": year, "label": f"x33fcon {str(year)[2:]}"},
                "title": title,
                "speakers": speakers[:4],
                "abstract": "",
                "track": None,
                "files": {
                    "slides": ("https://x33fcon.com" + slides_m.group(1)) if slides_m else None,
                    "whitepaper": None,
                    "tool": None,
                },
                "video_url": None,
                "source_url": f"https://x33fcon.com/#!archive/{year}/con.md",
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


def collect_year(year: int, log=None) -> dict:
    say = log or (lambda s: None)
    code, md = curl_get(f"https://x33fcon.com/archive/{year}/con.md", timeout=30)
    time.sleep(1.0)
    if code == 404:
        return {"status": "skipped", "meta": {"trace": [f"no archive for {year}"]}}
    if code != 200:
        return {"status": "failed", "meta": {"trace": [f"HTTP {code} for {year}"]}}
    records = parse_agenda_md(md, year)
    say(f"{year}: {len(records)} talks from markdown agenda")
    if not records:
        return {"status": "failed", "meta": {"trace": [f"{year}: agenda table not parsed"]}}
    return {
        "status": "ok",
        "kind": "records",
        "records": records,
        "meta": {"source": URL, "url": f"https://x33fcon.com/archive/{year}/con.md",
                 "title": f"x33fcon {year}", "trace": []},
    }


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

    def say(line: str):
        print(f"    {line}")

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for year in YEARS:
        key = f"x33f-{year}"
        if wanted and key not in wanted and str(year) not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, year))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    say(f"to crawl: {len(todo)} year(s)")

    for i, (key, year) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] x33fcon/{key}")
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
            print("    skipped")
        else:
            print("    FAILED")
    return captures
