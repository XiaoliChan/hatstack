"""DEF CON adapter — media.defcon.org static autoindex.

Editions are plain directories ("DEF CON 12/", "DEF CON 33/") each containing
"<edition> presentations/" (files named "DEF CON N - Speakers - Title.pdf")
and, in recent years, "<edition> villages/" (files named
"DEF CON N - <Village> Village - Speakers - Title.pdf", with occasional
"Vilage" typos and mp4s in Title-Speaker order).

The filename IS the metadata: no abstracts, but 30+ years of slides+video.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

ID = "defcon"
NAME = "DEF CON"
BASE = "https://media.defcon.org/"

_EDITION_RE = re.compile(r"^DEF CON (\d+)/?$")  # autoindex entries carry a trailing slash
_session = None


def _force_ipv4():
    """media.defcon.org's CDN drops IPv6 connections from this stack;
    urllib3 resolves AAAA first — pin the resolver to A records."""
    import socket

    import urllib3.util.connection as urllib3_cn

    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET


def _http_get(path: str) -> tuple[int, str]:
    """GET via subprocess curl: media.defcon.org's CDN refuses urllib3's TLS
    fingerprint (RemoteDisconnected) while curl passes. Runners ship curl."""
    import subprocess
    from urllib.parse import quote

    url = urljoin(BASE, quote(path, safe="/%"))
    p = subprocess.run(
        ["curl", "-4", "-sSL", "--max-time", "60",
         "-A", "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0.0.0 Safari/537.36",
         "-w", "\n%{http_code}", url],
        capture_output=True, text=True, timeout=90,
    )
    if p.returncode != 0 or "\n" not in p.stdout:
        return 0, ""
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return 0, ""


def get_listing(path: str, log=None) -> list[str]:
    """Entries (files+dirs) of an autoindex path, percent-decoded."""
    for attempt in range(3):
        code, text = _http_get(path)
        time.sleep(1.0)
        if code == 404:
            return []
        if code in (0, 429, 503):
            time.sleep(8 * (attempt + 1))
            continue
        if code != 200:
            if log:
                log(f"HTTP {code}: {path}")
            return []
        hrefs = re.findall(r'href="([^"?#]+)"', text)
        out = []
        for h in hrefs:
            if h.startswith(("http", "/", "#")):
                continue
            out.append(unquote(h))
        return out
    return []


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def parse_filename(name: str, edition_num: int) -> dict | None:
    """'DEF CON 32 - Speakers - Title.pdf' (or villages variants) -> record bits."""
    if not name.lower().endswith(".pdf"):
        return None
    stem = re.sub(r"\.pdf$", "", name, flags=re.I)
    stem = re.sub(rf"^DEF CON {edition_num}\s*-\s*", "", stem)
    parts = [p.strip() for p in stem.split(" - ") if p.strip()]
    if not parts:
        return None
    track = None
    if len(parts) >= 3 and parts[0].lower().rstrip("s").endswith(("village", "vilage")):
        track = parts.pop(0)
        track = track.replace("Vilage", "Village")
    if len(parts) >= 2:
        speakers, title = parts[0], " - ".join(parts[1:])
    else:
        speakers, title = "", parts[0]
    return {
        "title": title,
        "speakers_text": speakers,
        "track": track,
    }


def _match_video(videos: list[dict], talk: dict) -> str | None:
    """villages mp4s are 'Village - Title - Speakers'; presentations mp4s match
    the pdf stem minus suffix. Match on normalized title containment."""
    t = talk["title"].lower()
    for v in videos:
        if v["track"] == talk["track"] and (
            t in v["title"].lower() or v["title"].lower() in t
        ):
            return v["url"]
    return None


def collect_edition(edition: str, log=None) -> dict:
    """One edition -> capture dict with pre-parsed records."""
    m = _EDITION_RE.match(edition)
    num = int(m.group(1))
    year = 1992 + num
    label = f"DC {num}"
    listing_path = f"{edition}/{edition} presentations/"
    villages_url = urljoin(BASE, f"{edition}/{edition} villages/")
    files = get_listing(listing_path, log=log)
    say = log or (lambda s: None)
    say(f"{listing_path}: {len(files)} entries")
    if not files:
        return {"status": "failed", "meta": {"trace": [f"no presentations dir for {edition}"]}}

    village_files: list[str] = []
    for vname in (f"{edition} villages/", f"{edition} villages and creators/"):
        villages_path = f"{edition}/{vname}"
        village_files = get_listing(villages_path, log=log)
        if village_files:
            break

    records: list[dict] = []
    pdfs: list[tuple[str, dict]] = []
    videos: list[dict] = []

    for name in files + village_files:
        base_dir = listing_path if name in files else villages_url
        url = urljoin(urljoin(BASE, base_dir), name.replace(" ", "%20"))
        if name.lower().endswith(".pdf"):
            parsed = parse_filename(name, num)
            if parsed:
                pdfs.append((url, parsed))
        elif name.lower().endswith(".mp4"):
            stem = re.sub(r"\.mp4$", "", name, flags=re.I)
            stem = re.sub(rf"^DEF CON {num}\s*-\s*", "", stem)
            parts = [p.strip() for p in stem.split(" - ") if p.strip()]
            track = None
            if parts and parts[0].lower().rstrip("s").endswith(("village", "vilage")):
                track = parts.pop(0).replace("Vilage", "Village")
            videos.append({"track": track, "title": " - ".join(parts), "url": url})

    seen: set[str] = set()
    for url, parsed in pdfs:
        rid = f"dc{num}-{_slug(parsed['speakers_text'] + ' ' + parsed['title'])}"
        if rid in seen:
            continue
        seen.add(rid)
        speakers = [
            {"name": s.strip(), "company": None, "role": None}
            for s in re.split(r"\s{2,}|,|&| and ", parsed["speakers_text"])
            if 2 < len(s.strip()) < 40
        ]
        records.append(
            {
                "id": rid,
                "event": {"region": "us", "year": year, "label": label},
                "title": parsed["title"],
                "speakers": speakers[:6],
                "abstract": "",
                "track": parsed["track"],
                "files": {"slides": url, "whitepaper": None, "tool": None},
                "video_url": _match_video(videos, parsed),
                "source_url": urljoin(BASE, listing_path),
            }
        )
    say(f"{edition}: {len(records)} talks ({len(village_files)} village files)")
    return {
        "status": "ok",
        "kind": "records",
        "records": records,
        "meta": {"source": "media.defcon.org", "url": urljoin(BASE, listing_path),
                 "title": edition, "trace": []},
    }


def collect(ctx: dict) -> dict[str, dict]:
    import json

    cache_dir = Path(ctx["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, dict] = dict(ctx["cache_read"])
    if not captures:
        # load cache dir directly if ctx passed empty (report path)
        for f in sorted(cache_dir.glob("*.json")):
            try:
                captures[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue

    def say(line: str):
        print(f"    {line}")

    if ctx["use_cache"]:
        return captures

    root_entries = get_listing("", log=say)
    editions = [e.rstrip("/") for e in root_entries if _EDITION_RE.match(e)]
    editions.sort(key=lambda e: int(_EDITION_RE.match(e).group(1)), reverse=True)
    say(f"{len(editions)} editions found")

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for ed in editions:
        num = int(_EDITION_RE.match(ed).group(1))
        key = f"dc-{num}"
        if wanted and key not in wanted and ed not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, ed))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    say(f"to crawl: {len(todo)} edition(s)")

    for i, (key, ed) in enumerate(todo):
        print(f"[{i + 1}/{len(todo)}] defcon/{key} ({ed})")
        cap = collect_edition(ed, log=say)
        (cache_dir / f"{key}.json").write_text(
            json.dumps(cap, ensure_ascii=False), encoding="utf-8"
        )
        captures[key] = cap
        if cap.get("status") == "ok":
            print(f"    ok: {len(cap['records'])} talks")
        else:
            print("    FAILED")
    return captures
