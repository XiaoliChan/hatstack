"""Dataset assembly + completeness report from per-event captures."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .parse import parse_event_json, parse_legacy_html

REGION_ORDER = {"us": 0, "eu": 1, "asia": 2}


def build_records(event_key: str, capture: dict, conference: str = "blackhat") -> list[dict]:
    if capture.get("status") != "ok":
        return []
    region, year = event_key.split("-")[0], int(event_key.split("-")[1])
    event = {"region": region, "year": year, "source_url": capture.get("meta", {}).get("url")}
    if capture.get("kind") == "json":
        records = parse_event_json(event, capture["data"])
    else:
        records = parse_legacy_html(event, capture.get("html", ""))
    for r in records:
        r["conference"] = conference
    return records


def build_dataset(per_conf: dict[str, dict[str, dict]]) -> dict:
    records: list[dict] = []
    for conf_id, captures in per_conf.items():
        for key in sorted(captures):
            records.extend(build_records(key, captures[key], conference=conf_id))
    seen: set[str] = set()
    unique = []
    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        unique.append(r)
    unique.sort(key=lambda r: (-r["event"]["year"], REGION_ORDER.get(r["event"]["region"], 9), r["title"].lower()))
    conferences = sorted(
        c for c, caps in per_conf.items() if any(v.get("status") == "ok" for v in caps.values())
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
    per_event: dict[str, int] = {}
    for r in dataset["sessions"]:
        k = f"{r['conference']}/{r['event']['region']}-{r['event']['year']}"
        per_event[k] = per_event.get(k, 0) + 1
    report_events = {}
    for conf_id, captures in per_conf.items():
        for key in sorted(captures, key=lambda k: (-int(k.split("-")[1]) if k.split("-")[1].isdigit() else 0, k)):
            row_key = f"{conf_id}/{key}"
            cap = captures[key]
            meta = cap.get("meta", {})
            trace = meta.get("trace") or []
            base_note = f"li={cap.get('rendered_li')}" if cap.get("kind") == "json" else ""
            note = (base_note + " | " + trace[-1]) if trace else base_note
            lines.append(
                f"| {row_key} | {cap.get('status','?')} | {cap.get('kind','-')} | {per_event.get(row_key, 0)} | {note} |"
            )
            report_events[row_key] = {
                "status": cap.get("status"),
                "kind": cap.get("kind"),
                "sessions": per_event.get(row_key, 0),
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
