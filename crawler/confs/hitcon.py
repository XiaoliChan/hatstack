"""HITCON adapter — hitcon.org per-year agenda pages via the Wayback Machine
(live site 403s curl; wayback keeps static captures of most years).

Agenda blocks: li > a > h3 title, a <p> with the speaker, tag spans (tracks).
Slides are not linked on the agenda page — metadata-only records for now.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.wayback import wayback_get
from crawler.dataset import atomic_write_json

ID = "hitcon"
NAME = "HITCON"
YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016]

_SKIP_RE = re.compile(r"^(報到|開幕|閉幕|Break|break|Lunch|Tea|Closing|Opening)", )
_TRACK_STOP = {"Keynote", "線上演講", "即時問答", "演講", "Remote"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_agenda(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for a in soup.select("li a"):
        h3 = a.find("h3") or a.find(["h2", "h4"])
        if not h3:
            continue
        title = h3.get_text(" ", strip=True)
        if not title or len(title) < 6 or _SKIP_RE.match(title):
            continue
        p = a.find("p")
        speaker_line = p.get_text(" ", strip=True) if p else ""
        speaker_line = re.sub(r"\d+\s*min\.?$", "", speaker_line).strip()
        track = None
        for span in a.find_all("span"):
            t = span.get_text(" ", strip=True)
            if t and t not in _TRACK_STOP and len(t) < 12:
                track = t
                break
        records.append(
            {
                "id": f"hitcon{str(year)[2:]}-{_slug(title)}",
                "event": {"region": "asia", "year": year, "label": f"HITCON {str(year)[2:]}"},
                "title": title,
                "speakers": (
                    [{"name": speaker_line, "company": None, "role": None}]
                    if 2 < len(speaker_line) < 60
                    else []
                ),
                "abstract": "",
                "track": track,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": f"https://hitcon.org/{year}/agenda/",
            }
        )
    seen = set()
    out = []
    for r in records:
        k = r["title"].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def collect_year(year: int, log=None) -> dict:
    say = log or (lambda s: None)
    for path in (f"https://hitcon.org/{year}/agenda/",
                 f"https://hitcon.org/{year}/en/agenda/",
                 f"https://hitcon.org/{year}/"):
        ts = f"{year}1201" if year >= 2022 else f"{year + 1}0301"
        body = wayback_get(path, ts)
        if not body:
            continue
        html = body.decode("utf-8", "replace")
        records = parse_agenda(html, year)
        say(f"{path} (wayback {ts}): {len(records)} talks")
        if records:
            return {
                "status": "ok",
                "kind": "records",
                "records": records,
                "meta": {"source": "wayback", "url": path,
                         "title": f"HITCON {year}", "trace": []},
            }
    return {"status": "failed", "meta": {"trace": [f"no wayback capture for {year}"]}}


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

    def say(line: str):
        print(f"    {line}")

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for year in YEARS:
        key = f"hitcon-{year}"
        if wanted and key not in wanted and str(year) not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, year))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    say(f"to crawl: {len(todo)} year(s)")

    for i, (key, year) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] hitcon/{key}")
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
        else:
            print("    FAILED (no capture)")
    return captures
