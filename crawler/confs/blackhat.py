"""Black Hat adapter — the original hatstack crawler (wayback <=2025 + live >=2026)."""
from __future__ import annotations

import json
from pathlib import Path

from crawler import dataset as ds_mod
from crawler import events as ev_mod
from crawler.wayback import wayback_event, wayback_inventory

ID = "blackhat"
NAME = "Black Hat"
DESCRIPTION = "Information security conference series with US, Europe and Asia editions, running since 1997."
URL = "https://www.blackhat.com/"
WAYBACK_MAX_YEAR = 2025  # <=2025: wayback only (no Cloudflare); >=2026: live


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
    ds_mod.atomic_write_json(cache_dir / f"{key}.json", capture)


def _prepare_inventory(inventory: dict[str, dict]) -> dict[str, dict]:
    if inventory:
        return ev_mod.merge_candidates(inventory)
    return dict(ev_mod.fallback_events())


_EXTRA_2026 = {
    "eu-2026": [
        "https://www.blackhat.com/europe/briefings/schedule/index.html",
        "https://www.blackhat.com/archive/europe/2026/briefings/schedule/index.html",
        "https://www.blackhat.com/eu-26/briefings/schedule/index.html",
    ],
    "us-2026": [
        "https://www.blackhat.com/usa/briefings/schedule/index.html",
        "https://www.blackhat.com/archive/usa/2026/briefings/schedule/index.html",
        "https://www.blackhat.com/us-26/briefings/schedule/index.html",
    ],
}


def collect(ctx: dict) -> dict[str, dict]:
    cache_dir: Path = Path(ctx["cache_dir"])
    captures: dict[str, dict] = dict(ctx["cache_read"])

    if ctx["use_cache"]:
        return captures

    inventory = {}
    if not ctx["use_cache"]:
        html = wayback_inventory()
        if html:
            inventory = ev_mod.parse_inventory(html)
            print(f"inventory: {len(inventory)} events from archives.html (wayback)")
        else:
            print("wayback inventory unavailable -> generative fallback map")
    inventory = _prepare_inventory(inventory)
    # the archived archives.html predates the current year — always ensure the
    # latest editions exist as crawl targets (this is why 2026 vanished in v2)
    for year in (2025, 2026):
        for region in ("us", "eu", "asia"):
            key = f"{region}-{year}"
            if key not in inventory:
                cands = ev_mod.url_candidates(region, year)
                inventory[key] = {
                    "region": region, "year": year,
                    "urls": list(cands),
                    "kinds": {u: "json" if u.endswith("schedule/index.html") else "legacy"
                              for u in cands},
                }
    for key, urls in _EXTRA_2026.items():
        if key in inventory:
            for u in urls:
                if u not in inventory[key]["urls"]:
                    inventory[key]["urls"].insert(0, u)
                    inventory[key]["kinds"][u] = "json"  # schedule pages are XHR+render captures

    wanted = set(ctx["events"]) if ctx["events"] else None
    todo = []
    for key in sorted(inventory, key=lambda k: (-int(k.split("-")[1]), k)):
        if wanted and key not in wanted:
            continue
        if key in captures and captures[key].get("status") == "ok" and not ctx["refresh"]:
            continue
        todo.append((key, inventory[key]))
    if ctx["limit"]:
        todo = todo[: ctx["limit"]]
    wb_todo = [(k, e) for k, e in todo if e["year"] <= WAYBACK_MAX_YEAR]
    live_todo = [(k, e) for k, e in todo if e["year"] > WAYBACK_MAX_YEAR]
    print(f"[blackhat] to crawl: {len(todo)} (wayback {len(wb_todo)}, live {len(live_todo)}, "
          f"cached ok {sum(1 for c in captures.values() if c.get('status') == 'ok')})")

    for i, (key, event) in enumerate(wb_todo):
        print(f"[{i + 1}/{len(wb_todo)}] blackhat/{key} (wayback)")
        try:
            cap = wayback_event(event)
            _save_cache(cache_dir, key, cap)
            captures[key] = cap
            if cap.get("status") == "ok":
                print(f"    ok: {cap['kind']} ({len(ds_mod.build_records(key, cap))} records, "
                      f"{cap.get('meta', {}).get('title')})")
            else:
                print("    no wayback capture -> live fallback")
        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"    ERROR on {key}: {e!r} — continuing")
            captures[key] = {"status": "failed",
                             "meta": {"trace": [f"exception: {e!r}"]}}

    # wayback-missing events fall back to the live fresh-browser channel
    # (monthly cadence keeps this far below Cloudflare's trouble threshold)
    wb_missing = [k for k, e in wb_todo if captures.get(k, {}).get("status") != "ok"]

    live_todo = live_todo + [(k, e) for k, e in wb_todo if k in set(wb_missing)]
    if live_todo:
        from playwright.sync_api import sync_playwright

        from crawler.capture import crawl_event, pace

        with sync_playwright() as pw:
            for i, (key, event) in enumerate(live_todo):
                print(f"[{i + 1}/{len(live_todo)}] blackhat/{key} (live) -> {event['urls'][0]}")
                try:
                    cap = crawl_event(pw, event, attempts=6 if key in _EXTRA_2026 else 3)
                    _save_cache(cache_dir, key, cap)
                    captures[key] = cap
                    if cap.get("status") == "ok":
                        print(f"    ok: {cap['kind']} ({len(ds_mod.build_records(key, cap))} records)")
                    else:
                        print("    FAILED")
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    print(f"    ERROR on {key}: {e!r} — continuing")
                    captures[key] = {"status": "failed",
                                     "meta": {"trace": [f"exception: {e!r}"]}}
                if i < len(live_todo) - 1:
                    pace()
    return captures
