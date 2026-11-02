"""Dataset assembly + completeness report from per-event captures."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .parse import parse_event_json, parse_legacy_html

REGION_ORDER = {"us": 0, "eu": 1, "asia": 2}


def atomic_write_json(path: Path, data) -> None:
    """Write JSON via tmp+rename so a killed run never leaves a truncated
    cache file that silently vanishes from --use-cache rebuilds."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def build_records(event_key: str, capture: dict, conference: str = "blackhat") -> list[dict]:
    if capture.get("status") != "ok":
        return []
    if capture.get("kind") == "records":  # adapter pre-parsed (e.g. defcon)
        for r in capture["records"]:
            r["conference"] = conference
        return capture["records"]
    region, year = event_key.split("-")[0], int(event_key.split("-")[1])
    event = {"region": region, "year": year, "source_url": capture.get("meta", {}).get("url")}
    if capture.get("kind") == "json":
        records = parse_event_json(event, capture["data"])
    else:
        records = parse_legacy_html(event, capture.get("html", ""))
    for r in records:
        r["conference"] = conference
    return records


def build_dataset(per_conf: dict[str, dict[str, dict]], prior_sessions: list[dict] | None = None) -> dict:
    records: list[dict] = []
    captured: set[tuple[str, str, int]] = set()
    for conf_id, captures in per_conf.items():
        for key in sorted(captures):
            recs = build_records(key, captures[key], conference=conf_id)
            records.extend(recs)
            if captures[key].get("status") == "ok":
                for r in recs:
                    captured.add((conf_id, r["event"]["region"], r["event"]["year"]))
    # merge: keep prior sessions for events this run did not capture ok, so a
    # partial run (or an adapter that ran but captured nothing) never wipes
    # the committed dataset
    for s in prior_sessions or []:
        conf = s.setdefault("conference", "blackhat")
        ev = s.get("event", {})
        if (conf, ev.get("region"), ev.get("year")) not in captured:
            records.append(s)
    seen: set[str] = set()
    unique = []
    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        unique.append(r)
    unique.sort(key=lambda r: (-r["event"]["year"] if r["event"]["year"] > 0 else 1,
                               REGION_ORDER.get(r["event"]["region"], 9), r["title"].lower()))
    conference_ids = sorted(
        {r["conference"] for r in unique}
        | {c for c, caps in per_conf.items() if any(v.get("status") == "ok" for v in caps.values())}
    )
    # manifest (id/name/url/description) comes from the adapters themselves —
    # the site reads it from the dataset instead of hardcoding anything
    from importlib import import_module

    conferences = []
    for cid in conference_ids:
        try:
            mod = import_module(f"crawler.confs.{cid}")
            conferences.append({
                "id": cid,
                "name": getattr(mod, "NAME", cid),
                "url": getattr(mod, "URL", None),
                "description": getattr(mod, "DESCRIPTION", None),
            })
        except Exception:
            conferences.append({"id": cid, "name": cid, "url": None, "description": None})

    # editions index mirroring the site sidebar: conference -> edition -> ids
    # (sessions stay flat for search; this is the normalized view)
    editions: dict[str, dict] = {}
    for r in unique:
        conf = r["conference"]
        region, year = r["event"]["region"], r["event"]["year"]
        key = f"{conf}|{region}|{year}"
        e = editions.setdefault(key, {
            "key": key, "conference": conf, "region": region, "year": year,
            "label": "", "count": 0, "session_ids": [],
        })
        e["count"] += 1
        e["session_ids"].append(r["id"])
    regions_per_conf: dict[str, set] = {}
    for r in unique:
        regions_per_conf.setdefault(r["conference"], set()).add(r["event"]["region"])
    for e in editions.values():
        multi = len(regions_per_conf[e["conference"]]) > 1
        tag = e["region"].upper() if multi else None
        e["label"] = "-".join(str(x) for x in ([tag, e["year"]] if e["year"] > 0 else [tag, "unknown"]) if x)
    edition_list = sorted(
        editions.values(),
        key=lambda e: (
            conference_ids.index(e["conference"]),
            -(e["year"] if e["year"] > 0 else -1),  # newest first, unknown last
            e["region"],
        ),
    )
    return {
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conferences": conferences,
        "editions": edition_list,
        "sessions": unique,
    }


def build_report(per_conf: dict[str, dict[str, dict]], dataset: dict) -> tuple[str, dict]:
    lines = [
        "# Crawl completeness report",
        "",
        f"- dataset version: {dataset['version']}",
        f"- total sessions: {len(dataset['sessions'])}",
        f"- sessions with slides: {sum(1 for s in dataset['sessions'] if s['files']['slides'])}",
        f"- sessions with whitepaper: {sum(1 for s in dataset['sessions'] if s['files']['whitepaper'])}",
        f"- sessions with tool: {sum(1 for s in dataset['sessions'] if s['files']['tool'])}",
        f"- sessions with abstract: {sum(1 for s in dataset['sessions'] if s['abstract'])}",
    ]

    def _year_sort_key(key: str) -> tuple[int, str]:
        parts = key.split("-")
        year = -int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (year, key)

    conferences_report = []
    failed = []
    for conf_id, captures in per_conf.items():
        events = []
        md_rows = []
        for key in sorted(captures, key=_year_sort_key):
            cap = captures[key]
            meta = cap.get("meta", {})
            trace = meta.get("trace") or []
            base_note = f"li={cap.get('rendered_li')}" if cap.get("kind") == "json" else ""
            note = (base_note + " | " + trace[-1]) if trace else base_note
            # count this capture's own records — the capture key ("dc-33",
            # "38c3") doesn't match the dataset's region-year row keys, so
            # tallying from dataset sessions always showed 0
            n = len(build_records(key, cap, conference=conf_id))
            status = cap.get("status", "?")
            events.append({
                "key": key,
                "status": status,
                "kind": cap.get("kind"),
                "sessions": n,
                "url": meta.get("url"),
                "title": meta.get("title"),
                "note": note or None,
            })
            if status != "ok":
                failed.append(f"{conf_id}/{key}")
            md_rows.append(f"| {key} | {status} | {cap.get('kind','-')} | {n} | {note} |")
        lines.append("")
        lines.append(f"## {conf_id}")
        lines.append("")
        lines.append("| event | status | kind | sessions | note |")
        lines.append("|---|---|---|---|---|")
        lines.extend(md_rows)
        conferences_report.append({"id": conf_id, "events": events})
    lines.append("")
    lines.append(f"failed events: {', '.join(failed) if failed else 'none'}")
    return "\n".join(lines) + "\n", {
        "version": dataset["version"],
        "total": len(dataset["sessions"]),
        "conferences": conferences_report,
        "failed": failed,
    }


def write_outputs(dataset: dict, per_conf: dict[str, dict[str, dict]], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ds_path = out_dir / "dataset.json"
    ds_path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    report_md, report_json = build_report(per_conf, dataset)
    report_dir = out_dir / "report"
    report_dir.mkdir(exist_ok=True)
    # lightweight overview only — details live in per-conference report/*.md
    (report_dir / "summary.md").write_text(report_md, encoding="utf-8")

    # per-conference split files (mirrors the UI structure: manifest entry +
    # editions + that conference's sessions); site keeps the aggregate file
    by_dir = out_dir / "by-conference"
    by_dir.mkdir(exist_ok=True)
    conf_meta = {c["id"]: c for c in dataset.get("conferences", [])}
    for conf_id in conf_meta:
        sessions = [s for s in dataset["sessions"] if s.get("conference", "blackhat") == conf_id]
        atomic_write_json(by_dir / f"{conf_id}.json", {
            "version": dataset["version"],
            "conference": conf_meta[conf_id],
            "editions": [e for e in dataset.get("editions", []) if e["conference"] == conf_id],
            "sessions": sessions,
        })
    for cr in report_json.get("conferences", []):
        rows = [
            f"| {e['key']} | {e['status']} | {e['kind'] or '-'} | {e['sessions']} | {e['note'] or ''} |"
            for e in cr["events"]
        ]
        (report_dir / f"{cr['id']}.md").write_text(
            f"# {cr['id']} crawl report\n\n"
            "| event | status | kind | sessions | note |\n|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n",
            encoding="utf-8",
        )
    # site payload tier: tiny manifest (instant first paint) + versioned
    # sessions file (content-addressed -> immutable browser caching).
    # Nulls are stripped: 45k null fields were ~1MB of dead weight.
    def _slim(s: dict) -> dict:
        out = {}
        for k, v in s.items():
            if v is None or v == "" or v == []:
                continue
            if k == "files" and isinstance(v, dict):
                files = {fk: fv for fk, fv in v.items() if fv}
                if files:
                    out["files"] = files
                continue
            if k == "speakers":
                out["speakers"] = [{sk: sv for sk, sv in sp.items() if sv} for sp in v]
                continue
            out[k] = v
        return out

    manifest = {
        "version": dataset["version"],
        "total": len(dataset["sessions"]),
        "conferences": dataset.get("conferences", []),
        "editions": [
            {k: e[k] for k in ("key", "conference", "region", "year", "label", "count")}
            for e in dataset.get("editions", [])
        ],
    }
    atomic_write_json(out_dir / "manifest.json", manifest)
    slim_sessions = [_slim(s) for s in dataset["sessions"]]
    vtag = dataset["version"].replace(":", "")
    atomic_write_json(out_dir / f"sessions-v{vtag}.json", slim_sessions)
    return {"dataset": ds_path, "report_md": report_dir / "summary.md",
            "manifest": out_dir / "manifest.json",
            "sessions": out_dir / f"sessions-v{vtag}.json"}
