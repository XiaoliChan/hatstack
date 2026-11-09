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
    # 2003-2009 schedule-table microsites: the inventory (archived
    # archives.html) links the /archive/ canonical paths that have no IA
    # snapshots — inject the real archived schedule.html URLs so wayback
    # can find them regardless of what the inventory says
    from crawler.events import old_schedule_urls

    for reg in ("us", "eu", "asia"):
        for yr in range(2003, 2010):
            urls = old_schedule_urls(reg, yr)
            if not urls:
                continue
            key = f"{reg}-{yr}"
            entry = inventory.setdefault(
                key, {"region": reg, "year": yr, "urls": [], "kinds": {}}
            )
            for u in urls:
                if u not in entry["urls"]:
                    entry["urls"].insert(0, u)
                    entry["kinds"][u] = "legacy"
    # us-2013: the IA-served archives.html snapshot drifted and stopped
    # listing it (Nov 9) — guarantee the key exists so the day-page harvest
    # in the live section gets a chance to run
    inventory.setdefault("us-2013", {
        "region": "us", "year": 2013,
        "urls": [
            "https://www.blackhat.com/us-13/briefings.html",
            "https://www.blackhat.com/us-13/archives.html",
        ],
        "kinds": {
            "https://www.blackhat.com/us-13/briefings.html": "legacy",
            "https://www.blackhat.com/us-13/archives.html": "legacy",
        },
    })
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
            # us-2013: agenda lives on per-day schedule pages whose links
            # point to speaker pages, not PDFs — generic legacy acceptance
            # rejects them, so harvest both days and store pre-parsed records
            from crawler.parse import parse_us13_schedule

            _US13_DAYS = [
                "https://www.blackhat.com/us-13/schedule/briefings-31.html",
                "https://www.blackhat.com/us-13/schedule/briefings-01.html",
            ]
            if "us-2013" in {k for k, _ in live_todo}:
                recs13, trace13 = [], []
                for du in _US13_DAYS:
                    cap = crawl_event(
                        pw,
                        {"region": "us", "year": 2013, "urls": [du], "kinds": {du: "legacy"}},
                        attempts=3,
                    )
                    trace13 += cap.get("meta", {}).get("trace", [])
                    if cap.get("status") == "ok" and cap.get("html"):
                        recs13 += parse_us13_schedule(
                            {"region": "us", "year": 2013, "source_url": du}, cap["html"]
                        )
                if recs13:
                    seen_ids = set()
                    uniq13 = [r for r in recs13 if not (r["id"] in seen_ids or seen_ids.add(r["id"]))]
                    cap13 = {
                        "status": "ok", "kind": "records", "region": "us", "year": 2013,
                        "records": uniq13,
                        "meta": {"source": "live", "url": _US13_DAYS[0], "kind": "records",
                                 "title": "us-13 schedule days", "trace": trace13},
                    }
                    _save_cache(cache_dir, "us-2013", cap13)
                    captures["us-2013"] = cap13
                    print(f"    ok: us-2013 records ({len(uniq13)})")
                else:
                    print("    us-2013: no records from day pages")
            for i, (key, event) in enumerate(live_todo):
                if key == "us-2013":
                    continue  # harvested above from per-day schedule pages
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
