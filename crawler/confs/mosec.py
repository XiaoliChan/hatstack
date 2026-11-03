"""MOSEC adapter — mosec.org is dead from every live vantage (local + CI).
Wayback keeps the per-year microsites (2016-2019, Pangu Lab's mobile con)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.wayback import wayback_get

ID = "mosec"
NAME = "MOSEC"
URL = "https://mosec.org/"
DESCRIPTION = "Mobile Security Conference by Pangu Lab, Shanghai, 2016-2019."
YEARS = [2019, 2018, 2017, 2016]
_SKIP = re.compile(r"^(registration|venue|agenda|schedule|cfp|sponsor|about|home|contact)", re.I)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_year_html(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    seen: set[str] = set()
    for block in soup.select("div, section, article, li"):
        h = block.find(["h2", "h3", "h4", "h5", "b", "strong"], recursive=False)
        if not h:
            continue
        title = h.get_text(" ", strip=True)
        if not title or len(title) < 8 or _SKIP.match(title):
            continue
        pdf = block.find("a", href=re.compile(r"\.pdf$", re.I))
        yt = block.find("a", href=re.compile(r"youtube\.com|youtu\.be", re.I))
        if not (pdf or yt):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "id": f"mosec{str(year)[2:]}-{_slug(title)}",
            "event": {"region": "asia", "year": year, "label": f"MOSEC {str(year)[2:]}"},
            "title": title,
            "speakers": [],
            "abstract": block.get_text(" ", strip=True)[:400],
            "track": None,
            "files": {"slides": pdf["href"] if pdf else None,
                      "whitepaper": None, "tool": None},
            "video_url": yt["href"] if yt else None,
            "source_url": f"https://mosec.org/{year}/",
        })
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

    def say(line: str):
        print(f"    {line}")

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for year in YEARS:
        key = f"mosec-{year}"
        if wanted and key not in wanted and str(year) not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, year))
    say(f"to crawl: {len(todo)} year(s)")

    for i, (key, year) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] mosec/{key}")
        try:
            body = wayback_get(f"https://mosec.org/{year}/")
            if not body:
                body = wayback_get("https://mosec.org/")
            cap = {"status": "failed", "meta": {"trace": [f"no capture for {year}"]}}
            if body:
                html = body.decode("utf-8", "replace")
                recs = parse_year_html(html, year)
                say(f"{year}: {len(recs)} talks")
                if recs:
                    cap = {"status": "ok", "kind": "records", "records": recs,
                           "meta": {"source": URL, "url": f"https://mosec.org/{year}/",
                                    "title": f"MOSEC {year}", "trace": []}}
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
            print("    FAILED")
    return captures
