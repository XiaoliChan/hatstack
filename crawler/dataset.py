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
    conferences = sorted(
        {r["conference"] for r in unique}
        | {c for c, caps in per_conf.items() if any(v.get("status") == "ok" for v in caps.values())}
    )
    return {
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conferences": conferences,
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
        "",
        "| event | status | kind | sessions | note |",
        "|---|---|---|---|---|",
    ]
    def _year_sort_key(key: str) -> tuple[int, str]:
        parts = key.split("-")
        year = -int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (year, key)

    report_events = {}
    for conf_id, captures in per_conf.items():
        for key in sorted(captures, key=_year_sort_key):
            row_key = f"{conf_id}/{key}"
            cap = captures[key]
            meta = cap.get("meta", {})
            trace = meta.get("trace") or []
            base_note = f"li={cap.get('rendered_li')}" if cap.get("kind") == "json" else ""
            note = (base_note + " | " + trace[-1]) if trace else base_note
            # count this capture's own records — the capture key ("dc-33",
            # "38c3") doesn't match the dataset's region-year row keys, so
            # tallying from dataset sessions always showed 0
            n = len(build_records(key, cap, conference=conf_id))
            lines.append(
                f"| {row_key} | {cap.get('status','?')} | {cap.get('kind','-')} | {n} | {note} |"
            )
            report_events[row_key] = {
                "status": cap.get("status"),
                "kind": cap.get("kind"),
                "sessions": n,
                "url": meta.get("url"),
                "title": meta.get("title"),
            }
    return "\n".join(lines) + "\n", {"events": report_events, "total": len(dataset["sessions"])}


def write_outputs(dataset: dict, per_conf: dict[str, dict[str, dict]], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ds_path = out_dir / "dataset.json"
    ds_path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    report_md, report_json = build_report(per_conf, dataset)
    (out_dir / "report.json").write_text(
        json.dumps(report_json, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")
    return {"dataset": ds_path, "report_md": out_dir / "report.md", "report": out_dir / "report.json"}
