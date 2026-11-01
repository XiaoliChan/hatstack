"""CCC adapter — api.media.ccc.de (VOC recordings).

media.ccc.de hosts 467 conferences; we curate the security/hacker-relevant
series: Congress (NNc3), CCC Camp, GPN, Easterhegg, MRMCD, Datenspuren,
FiffKon, DIVOC. Events carry title/abstract/persons + a player link; slides
rarely exist as separate files there, so files stay empty and video_url
points to the media.ccc.de player.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

from crawler.dataset import atomic_write_json

ID = "ccc"
NAME = "CCC"
API = "https://api.media.ccc.de/public"

_SERIES_RES = [
    re.compile(p, re.I)
    for p in (
        r"^\d{1,2}c3$",          # 16C3 … 39C3
        r"^(cc)?camp\d*$",       # camp2019 / cccamp23
        r"^gpn\d+$",             # GPN
        r"^eh\d+$",               # Easterhegg
        r"^mrmcd[\da-z]+$",      # MRMCD
        r"^(ds\d{4}|datenspuren)$",
        r"^fiffkon\d+$",
        r"^divoc",
        r"^froscon\d+$",         # FrOSCon (security-relevant talks, ~20 editions)
    )
]

_session = None


def _s() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0.0.0 Safari/537.36"}
        )
    return _session


def _api_get(path: str, log=None) -> dict | None:
    for attempt in range(3):
        try:
            r = _s().get(f"{API}{path}", timeout=60)
            time.sleep(1.0)
            if r.status_code in (429, 503):
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code != 200:
                if log:
                    log(f"HTTP {r.status_code}: {path}")
                return None
            return r.json()
        except Exception as e:
            if log:
                log(f"fetch error {e!r}: {path}")
            time.sleep(5)
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def _strip_html(text) -> str:
    if not text:
        return ""
    from bs4 import BeautifulSoup

    return BeautifulSoup(str(text), "lxml").get_text(" ", strip=True)


def curated_conferences(log=None) -> list[dict]:
    data = _api_get("/conferences", log=log) or {}
    out = []
    for c in data.get("conferences", []):
        a = c.get("acronym", "")
        if any(rx.match(a) for rx in _SERIES_RES):
            out.append(c)
    out.sort(key=lambda c: c.get("acronym", ""))
    return out


def collect_conference(conf: dict, log=None) -> dict:
    acronym = conf["acronym"]
    data = _api_get(f"/conferences/{quote(acronym)}", log=log)
    if not data or not data.get("events"):
        return {"status": "failed",
                "meta": {"trace": [f"no events for {acronym}"]}}
    say = log or (lambda s: None)
    years = [e["date"][:4] for e in data["events"] if e.get("date")]
    year = int(max(set(years), key=years.count)) if years else 0
    label = acronym.upper()
    records = []
    for e in data["events"]:
        title = _strip_html(e.get("title"))
        if not title:
            continue
        subtitle = _strip_html(e.get("subtitle"))
        if subtitle:
            title = f"{title} - {subtitle}"
        records.append(
            {
                "id": f"ccc-{_slug(acronym)}-{_slug(title)}",
                "event": {"region": "eu", "year": year, "label": label},
                "title": title,
                "speakers": [
                    {"name": p, "company": None, "role": None}
                    for p in (e.get("persons") or [])
                    if isinstance(p, str) and p.strip()
                ][:6],
                "abstract": _strip_html(e.get("description"))[:4000],
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": e.get("frontend_link"),
                "source_url": e.get("frontend_link"),
            }
        )
    say(f"{acronym}: {len(records)} events ({year})")
    return {
        "status": "ok",
        "kind": "records",
        "records": records,
        "meta": {"source": "api.media.ccc.de", "url": f"{API}/conferences/{acronym}",
                 "title": acronym, "trace": []},
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

    confs = curated_conferences(log=say)
    say(f"{len(confs)} curated conferences")

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for c in confs:
        key = c["acronym"].lower()
        if wanted and key not in wanted and c["acronym"] not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, c))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    say(f"to crawl: {len(todo)} conference(s)")

    for i, (key, c) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] ccc/{key}")
        try:
            cap = collect_conference(c, log=say)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"    ERROR: {e!r} — continuing")
            cap = {"status": "failed", "meta": {"trace": [f"exception: {e!r}"]}}
        atomic_write_json(cache_dir / f"{key}.json", cap)
        captures[key] = cap
        if cap.get("status") == "ok":
            print(f"    ok: {len(cap['records'])} events")
        else:
            print("    FAILED")
    return captures
