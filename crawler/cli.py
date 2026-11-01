"""CLI: python -m crawler crawl|download|report"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import dataset as ds_mod
from . import events as ev_mod
from .wayback import wayback_event, wayback_inventory

WAYBACK_MAX_YEAR = 2025  # <=2025: wayback only (no Cloudflare); >=2026: live


def _prepare_inventory(inventory: dict[str, dict]) -> dict[str, dict]:
    """Inventory links only the /archive/ canonical path (hard-blocked);
    merge generative microsite candidates into every event."""
    return ev_mod.merge_candidates(inventory) if inventory else dict(ev_mod.fallback_events())

BASE = Path(__file__).resolve().parent
DEFAULT_CACHE = BASE / "cache"


def _load_cache(cache_dir: Path) -> dict[str, dict]:
    caps: dict[str, dict] = {}
    if not cache_dir.exists():
        return caps
    for f in sorted(cache_dir.glob("*.json")):
        try:
            caps[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
    return caps


def _save_cache(cache_dir: Path, key: str, capture: dict):
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(
        json.dumps(capture, ensure_ascii=False), encoding="utf-8"
    )


def cmd_crawl(args) -> int:
    cache_dir = Path(args.cache_dir)
    captures = _load_cache(cache_dir)

    inventory = {}
    if not args.use_cache:
        html = wayback_inventory()  # plain requests, no browser
        if html:
            inventory = ev_mod.parse_inventory(html)
            print(f"inventory: {len(inventory)} events from archives.html (wayback)")
        else:
            print("wayback inventory unavailable -> generative fallback map")
    inventory = _prepare_inventory(inventory)

    wanted = set(args.events) if args.events else None
    todo = []
    for key in sorted(inventory, key=lambda k: (-int(k.split("-")[1]), k)):
        if wanted and key not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not args.refresh:
            continue
        todo.append((key, inventory[key]))
    if args.limit:
        todo = todo[: args.limit]
    wb_todo = [(k, e) for k, e in todo if e["year"] <= WAYBACK_MAX_YEAR]
    live_todo = [(k, e) for k, e in todo if e["year"] > WAYBACK_MAX_YEAR]
    print(f"to crawl: {len(todo)} event(s) "
          f"(wayback {len(wb_todo)}, live {len(live_todo)}, "
          f"cached ok {sum(1 for c in captures.values() if c.get('status') == 'ok')})")

    for i, (key, event) in enumerate(wb_todo):
        print(f"[{i + 1}/{len(wb_todo)}] {key} (wayback)")
        cap = wayback_event(event)
        _save_cache(cache_dir, key, cap)
        captures[key] = cap
        if cap.get("status") == "ok":
            n = len(ds_mod.build_records(key, cap))
            print(f"    ok: {cap['kind']} ({n} records, {cap.get('meta', {}).get('title')})")
        else:
            print("    FAILED (no usable wayback capture)")

    if live_todo:
        from playwright.sync_api import sync_playwright  # only for >=2026 events

        from .capture import crawl_event, pace

        with sync_playwright() as pw:
            for i, (key, event) in enumerate(live_todo):
                print(f"[{i + 1}/{len(live_todo)}] {key} (live) -> {event['urls'][0]}")
                cap = crawl_event(pw, event)
                _save_cache(cache_dir, key, cap)
                captures[key] = cap
                if cap.get("status") == "ok":
                    n = len(ds_mod.build_records(key, cap))
                    print(f"    ok: {cap['kind']} ({n} records)")
                else:
                    print("    FAILED")
                if i < len(live_todo) - 1:
                    pace()

    out = ds_mod.write_outputs(
        ds_mod.build_dataset(captures), captures, Path(args.out)
    )
    print(f"dataset -> {out['dataset']}")
    print(f"report  -> {out['report_md']}")
    return 0


def cmd_download(args) -> int:
    import requests

    ds_path = Path(args.dataset)
    data = json.loads(ds_path.read_text(encoding="utf-8"))
    sessions = data["sessions"]
    if args.event:
        label = args.event.upper()
        sessions = [s for s in sessions if s["event"]["label"].upper() == label]
        if not sessions:
            print(f"no sessions for event {args.event} in {ds_path}")
            return 1
    types = [t.strip() for t in args.types.split(",") if t.strip()]
    urls: list[tuple[str, str]] = []
    for s in sessions:
        for t in types:
            u = s["files"].get(t)
            if u:
                urls.append((s["event"]["label"], u))
    dest = Path(args.dest)
    ok = skip = fail = 0
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0.0.0 Safari/537.36"}
    for label, url in urls:
        target = dest / label / url.rsplit("/", 1)[-1]
        if target.exists() and target.stat().st_size > 0:
            skip += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with requests.get(url, headers=headers, timeout=90, stream=True) as r:
                if r.status_code != 200:
                    fail += 1
                    print(f"HTTP {r.status_code} {url}")
                    continue
                with open(target, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"ERR {url}: {e!r}")
        time.sleep(0.4)
    print(f"downloaded {ok}, skipped(existing) {skip}, failed {fail} -> {dest}")
    return 0 if fail == 0 else 2


def cmd_report(args) -> int:
    ds_path = Path(args.dataset)
    data = json.loads(ds_path.read_text(encoding="utf-8"))
    captures = _load_cache(Path(args.cache_dir))
    out = ds_mod.write_outputs(data, captures, ds_path.parent)
    print(f"report -> {out['report_md']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crawler", description="BlackHat briefings crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("crawl", help="crawl events -> dataset")
    p.add_argument("--events", nargs="*", help="event keys, e.g. us-24 asia-21")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--refresh", action="store_true", help="ignore cache, re-crawl everything")
    p.add_argument("--use-cache", action="store_true", help="no network; rebuild from cache only")
    p.add_argument("--out", default="dataset", help="output dir (dataset.json + reports)")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("download", help="bulk download PDFs from dataset")
    p.add_argument("--event", help="event label, e.g. US-24 (omit for all)")
    p.add_argument("--types", default="slides,whitepaper", help="slides,whitepaper,tool")
    p.add_argument("--dest", default="save")
    p.add_argument("--dataset", default="dataset/dataset.json")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("report", help="regenerate report from dataset + cache")
    p.add_argument("--dataset", default="dataset/dataset.json")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    p.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
