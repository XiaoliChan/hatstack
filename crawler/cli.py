"""CLI: python -m crawler crawl|download|report [--confs blackhat defcon ...]"""
from __future__ import annotations

import argparse
import faulthandler
import json
import sys
import time
from pathlib import Path

from crawler import confs
from crawler import dataset as ds_mod

# C-level crashes (lxml/openssl aborts) bypass Python's exception printing and
# can take the stdout buffer with them — enable core-style tracebacks now.
faulthandler.enable()

BASE = Path(__file__).resolve().parent
DEFAULT_CACHE = BASE / "cache"


def _load_conf_caches(cache_root: Path, ids: list[str] | None) -> dict[str, dict[str, dict]]:
    """per-conference captures from cache dirs (no network)."""
    per_conf: dict[str, dict[str, dict]] = {}
    for adapter in confs.adapters(ids):
        cdir = cache_root / adapter.ID
        caps: dict[str, dict] = {}
        if cdir.exists():
            for f in sorted(cdir.glob("*.json")):
                try:
                    caps[f.stem] = json.loads(f.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"warning: unreadable cache file {f.name}: {e!r}")
                    continue
        per_conf[adapter.ID] = caps
    return per_conf


def cmd_crawl(args) -> int:
    cache_root = Path(args.cache_dir)
    # prefill with cached captures so ctx["cache_read"] is real data, not a
    # misleading always-empty dict
    per_conf: dict[str, dict[str, dict]] = _load_conf_caches(cache_root, args.confs)
    for adapter in confs.adapters(args.confs):
        print(f"=== {adapter.NAME} ({adapter.ID}) ===")
        ctx = {
            "events": [e for tok in (args.events or []) for e in tok.split(",") if e],
            "limit": args.limit,
            "refresh": args.refresh,
            "use_cache": args.use_cache,
            "cache_dir": cache_root / adapter.ID,
            "cache_read": per_conf.get(adapter.ID, {}),
        }
        per_conf[adapter.ID] = adapter.collect(ctx)

    prior: list[dict] = []
    prior_path = Path(args.out) / "dataset.json"
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text(encoding="utf-8")).get("sessions", [])
            print(f"merging with committed dataset ({len(prior)} prior sessions)")
        except Exception:
            prior = []

    out = ds_mod.write_outputs(
        ds_mod.build_dataset(per_conf, prior_sessions=prior), per_conf, Path(args.out)
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
    per_conf = _load_conf_caches(Path(args.cache_dir), args.confs)
    out = ds_mod.write_outputs(data, per_conf, ds_path.parent)
    print(f"report -> {out['report_md']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crawler", description="Security-conference crawler")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("crawl", help="crawl conferences -> dataset")
    p.add_argument("--confs", nargs="*", default=None,
                   help="conference ids (default: all registered adapters)")
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
    p.add_argument("--confs", nargs="*", default=None)
    p.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
