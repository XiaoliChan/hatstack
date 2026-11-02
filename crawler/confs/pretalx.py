"""Generic Pretalx adapter — any conference on a Pretalx instance.

Pretalx serves frab-schema schedule JSON at
  <instance>/<event>/schedule/export/schedule.json   (or /schedule/schedule.json)
with days -> rooms -> talks: title, persons, abstract, and links[]
(attachments carry slides). One adapter serves any Pretalx-hosted conf via
INSTANCES (added as they're confirmed by recon).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from crawler.net import curl_get

ID = "pretalx"
NAME = "Pretalx conferences"
URL = "https://pretalx.com/p/about/"
DESCRIPTION = "Conferences hosted on Pretalx (e.g. SEC-T)."

# instance -> editions (slug, year); 404 editions are skipped harmlessly
INSTANCES: dict[str, list[tuple[str, int]]] = {
    "sec-t": {
        "url": "https://event.sec-t.org",
        "region": "eu",
        "label": "SEC-T",
        "editions": [(f"sec-t-{y}", y) for y in range(2026, 2017, -1)],
    },
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def collect_edition(instance: str, conf: dict, slug: str, year: int, log=None) -> dict:
    say = log or (lambda s: None)
    base = conf["url"]
    for path in (f"{base}/{slug}/schedule/export/schedule.json",
                 f"{base}/{slug}/schedule/schedule.json"):
        code, body = curl_get(path, timeout=40)
        time.sleep(1.5)
        if code == 200 and body:
            break
    else:
        return {"status": "skipped", "meta": {"trace": [f"no schedule json for {slug}"]}}
    try:
        data = json.loads(body)
    except Exception as e:
        return {"status": "failed", "meta": {"trace": [f"{slug}: bad json {e!r}"]}}

    # pretalx export: days[].rooms is a {room_name: [talks]} dict; frab
    # export uses [{name, talks}] lists — handle both
    talks = []
    for day in data.get("schedule", {}).get("conference", {}).get("days", []):
        rooms = day.get("rooms") or {}
        if isinstance(rooms, dict):
            for talk_list in rooms.values():
                talks.extend(talk_list or [])
        else:
            for room in rooms:
                talks.extend(room.get("talks", []) or [])
    records = []
    for t in talks:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        slides = None
        video = None
        for l in t.get("links", []) or []:
            url = l.get("url") if isinstance(l, dict) else None
            if not url:
                continue
            if ".pdf" in url.lower() and not slides:
                slides = url
            elif ("youtube" in url or "youtu.be" in url) and not video:
                video = url
        rec = t.get("recording", {}) or {}
        vurl = rec.get("url") if isinstance(rec, dict) else None
        records.append(
            {
                "id": f"{instance}{str(year)[2:]}-{_slug(title)}",
                "event": {"region": conf["region"], "year": year,
                          "label": f"{conf['label']} {str(year)[2:]}"},
                "title": title,
                "speakers": [
                    {"name": p.get("public_name") or p.get("name"), "company": None, "role": None}
                    for p in (t.get("persons") or [])
                    if (p.get("public_name") or p.get("name"))
                ][:6],
                "abstract": (t.get("abstract") or "")[:4000],
                "track": t.get("track"),
                "files": {"slides": slides, "whitepaper": None, "tool": None},
                "video_url": video or vurl,
                "source_url": t.get("url") or f"{base}/{slug}/schedule/",
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
    say(f"{slug}: {len(out)} talks")
    if not out:
        return {"status": "skipped", "meta": {"trace": [f"{slug}: 0 talks"]}}
    return {
        "status": "ok",
        "kind": "records",
        "records": out,
        "meta": {"source": base, "url": f"{base}/{slug}/", "title": slug, "trace": []},
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
    for instance, conf in INSTANCES.items():
        for slug, year in conf["editions"]:
            key = f"{instance}-{year}"
            if wanted and key not in wanted and slug not in wanted:
                continue
            if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
                continue
            print(f"[pretalx] {key}")
            try:
                cap = collect_edition(instance, conf, slug, year, log=say)
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"    ERROR: {e!r} — continuing")
                cap = {"status": "failed", "meta": {"trace": [f"exception: {e!r}"]}}
            atomic_write_json(cache_dir / f"{key}.json", cap)
            captures[key] = cap
            if cap.get("status") == "ok":
                print(f"    ok: {len(cap['records'])} talks")
    return captures
