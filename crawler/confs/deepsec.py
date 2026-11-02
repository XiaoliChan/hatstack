"""DeepSec adapter — deepsec.net/docs/ is an Apache autoindex (like
media.defcon.org). Structure: /docs/ lists directories (Album/Audio/Slides...)
and per-year talk material. Filename carries speaker+title like DEF CON."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

from crawler.net import curl_get

ID = "deepsec"
NAME = "DeepSec"
URL = "https://deepsec.net/"
DESCRIPTION = "DeepSec Deep Security Conference, Vienna, since 2007."
BASE = "https://deepsec.net/docs/"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


def get_listing(path: str, log=None) -> list[str]:
    for attempt in range(3):
        code, text = curl_get(urljoin(BASE, quote(path, safe="/%")), timeout=40)
        time.sleep(1.0)
        if code == 200 and text:
            return [unquote(h) for h in re.findall(r'href="([^"?#]+)"', text)
                    if not h.startswith(("http", "/", "#"))]
        if code in (429, 503):
            time.sleep(8 * (attempt + 1))
            continue
        break
    return []


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
    if ctx["use_cache"] or ("all" in captures and captures["all"].get("status") == "ok"
                            and not ctx["refresh"]):
        return captures

    def say(line: str):
        print(f"    {line}")

    trace: list[str] = []
    records = []
    seen: set[str] = set()

    top = get_listing("", log=say)
    trace.append(f"/docs/: {len(top)} entries -> {top[:12]}")
    say(trace[-1])
    # recurse one level into every non-media directory (top level also has
    # loose PDFs)
    interesting = [e for e in top
                   if e.endswith("/") and e.split("/")[0].upper() not in
                   ("ALBUM", "AUDIO", "BANNER", "VIDEO", "VIDEOS", "IMAGES", "IMG")]
    for name in top:
        if name.lower().endswith(".pdf") and "/" not in name:
            interesting.append(name)  # handled below as loose file marker
    interesting = [e for e in interesting if e.endswith("/")]
    loose_pdfs = [e for e in top if e.lower().endswith(".pdf")]
    for d in interesting:
        sub = get_listing(d, log=say)
        trace.append(f"{d}: {len(sub)} entries")
        say(trace[-1])
        for name in sub:
            if not name.lower().endswith(".pdf"):
                continue
            stem = re.sub(r"\.pdf$", "", name, flags=re.I)
            parts = [p.strip() for p in re.split(r"[-_]", stem) if p.strip()]
            year_m = re.search(r"(20\d\d)", name)
            year = int(year_m.group(1)) if year_m else 0
            title = " ".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else stem)
            key = stem.lower()
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "id": f"deepsec-{_slug(stem)[:60]}",
                "event": {"region": "eu", "year": year, "label": "DeepSec"},
                "title": title or stem,
                "speakers": ([{"name": parts[0], "company": None, "role": None}]
                             if parts and len(parts) > 1 else []),
                "abstract": "",
                "track": None,
                "files": {"slides": urljoin(urljoin(BASE, d), quote(name)),
                          "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": BASE,
            })

    cap = {
        "status": "ok" if records else "failed",
        "kind": "records",
        "records": records,
        "meta": {"source": BASE, "url": BASE, "title": "DeepSec", "trace": trace},
    }
    atomic_write_json(cache_dir / "all.json", cap)
    (cache_dir / "listing.txt").write_text("\n".join(trace), encoding="utf-8")
    captures["all"] = cap
    print(f"    DeepSec total: {len(records)} talks")
    return captures
