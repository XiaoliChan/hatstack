"""Conference adapter registry.

Each adapter is a module under crawler/confs/ exposing:
    ID   - short id used in dataset records and cache dirs ("blackhat")
    NAME - display name ("Black Hat")
    collect(ctx) -> dict[str, dict]   # {event_key: capture}

ctx is a dict with: events (set|None), limit (int), refresh (bool),
use_cache (bool), cache_dir (Path), cache_read (dict pre-loaded captures),
cache_write(callable key->None).
"""

_REGISTRY = ["blackhat", "defcon", "ccc", "offensivecon", "usenix", "x33fcon", "redteamvillage"]


def adapters(ids: list[str] | None = None):
    from importlib import import_module

    wanted = ids or list(_REGISTRY)
    for conf_id in wanted:
        if conf_id not in _REGISTRY:
            raise SystemExit(f"unknown conference adapter: {conf_id}")
        yield import_module(f"crawler.confs.{conf_id}")
