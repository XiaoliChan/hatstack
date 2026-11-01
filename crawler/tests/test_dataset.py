import json

import pytest

from crawler.confs.defcon import _match_video, clean_title, parse_filename
from crawler.confs.usenix import parse_people
from crawler.dataset import build_dataset, build_report


def _records(conf, region, year, n=2):
    return [
        {
            "id": f"{conf}{year}-{i}",
            "event": {"region": region, "year": year, "label": f"{conf.upper()} {year}"},
            "title": f"{conf} talk {i}",
            "speakers": [],
            "abstract": "",
            "track": None,
            "files": {"slides": None, "whitepaper": None, "tool": None},
            "video_url": None,
            "source_url": None,
        }
        for i in range(n)
    ]


def _capture(records, status="ok", kind="records"):
    return {"status": status, "kind": kind, "records": records, "meta": {"url": "x"}}


def test_prior_sessions_kept_when_conference_not_crawled():
    prior = _records("blackhat", "us", 2024, n=1)
    ds = build_dataset({"defcon": {"dc-33": _capture(_records("defcon", "us", 2025))}}, prior)
    ids = {r["id"] for r in ds["sessions"]}
    assert "blackhat2024-0" in ids
    assert "defcon2025-0" in ids


def test_failed_adapter_run_never_wipes_its_conference():
    """An adapter that ran but captured nothing ok must not drop committed
    sessions (this wiped all 226 Black Hat sessions in the Nov 2025 dataset)."""
    prior = _records("blackhat", "us", 2024) + _records("blackhat", "us", 2016)
    per_conf = {
        "blackhat": {"us-24": _capture([], status="failed")},
        "defcon": {"dc-34": _capture(_records("defcon", "us", 2026))},
    }
    ds = build_dataset(per_conf, prior)
    ids = {r["id"] for r in ds["sessions"]}
    assert "blackhat2024-0" in ids
    assert "blackhat2016-0" in ids
    assert "defcon2026-0" in ids


def test_recrawled_event_replaces_only_that_event():
    prior = (
        _records("defcon", "us", 2025, n=1)
        + _records("defcon", "us", 2026, n=1)
        + _records("blackhat", "us", 2024, n=1)
    )
    per_conf = {"defcon": {"dc-34": _capture(_records("defcon", "us", 2026, n=3))}}
    ds = build_dataset(per_conf, prior)
    ids = {r["id"] for r in ds["sessions"]}
    # dc-34 was re-captured: old 2026 sessions replaced by fresh ones
    assert "defcon2026-0" in ids
    assert sum(1 for r in ds["sessions"] if r["event"]["year"] == 2026) == 3
    # untouched events survive
    assert "defcon2025-0" in ids
    assert "blackhat2024-0" in ids


def test_prior_sessions_get_conference_backfilled():
    prior = [{"id": "us24-1", "event": {"region": "us", "year": 2024}, "title": "t",
              "files": {"slides": None}}]
    ds = build_dataset({"defcon": {"dc-33": _capture(_records("defcon", "us", 2025))}}, prior)
    old = next(r for r in ds["sessions"] if r["id"] == "us24-1")
    assert old["conference"] == "blackhat"
    assert any(c["id"] == "blackhat" for c in ds["conferences"])


def test_use_cache_run_with_empty_adapters_keeps_everything():
    per_conf = {aid: {} for aid in ("blackhat", "hitcon", "kcon", "redteamvillage", "x33fcon")}
    prior = _records("blackhat", "us", 2016, n=2)
    ds = build_dataset(per_conf, prior)
    assert len(ds["sessions"]) == 2


def test_report_handles_hyphenless_cache_keys():
    per_conf = {"ccc": {"38c3": _capture(_records("ccc", "eu", 2024))}}
    ds = build_dataset(per_conf)
    md, report = build_report(per_conf, ds)
    assert "| 38c3 | ok | records | 2 |" in md
    ccc = next(c for c in report["conferences"] if c["id"] == "ccc")
    assert next(e for e in ccc["events"] if e["key"] == "38c3")["sessions"] == 2


def test_clean_title_strips_media_server_marker():
    assert (
        clean_title("8 Out of 10 Banks in Belgium HATE This One Weird eID RCE - MEDIA SERVER Belgi")
        == "8 Out of 10 Banks in Belgium HATE This One Weird eID RCE"
    )


def test_clean_title_strips_version_markers_and_dup_suffix():
    assert clean_title("Bird Hunting Season The Final Flight - PDF v1") == "Bird Hunting Season The Final Flight"
    assert clean_title("Beyond the Ceremony The 2026 Passkey Attack Surface - v2") == "Beyond the Ceremony The 2026 Passkey Attack Surface"
    assert clean_title("Compounding Interest Exploiting the ATM Supply Chain - Burch (2)") == "Compounding Interest Exploiting the ATM Supply Chain - Burch"
    assert clean_title("A Plain Title") == "A Plain Title"


def test_parse_filename_dedupes_versioned_files_to_same_slug():
    a = parse_filename("DEF CON 34 - Jon Gaines - Bird Hunting Season The Final Flight - PDF v1.pdf", 34)
    b = parse_filename("DEF CON 34 - Jon Gaines - Bird Hunting Season The Final Flight - v1.pdf", 34)
    assert a["title"] == b["title"]


def test_match_video_ignores_track_spelling_case():
    talk = {"title": "Of Stochastic Parrots", "track": "Crypto & Privacy Village"}
    vids = [{"track": "crypto & privacy village", "title": "Of Stochastic Parrots", "url": "v1"}]
    assert _match_video(vids, talk) == "v1"


def test_match_video_no_cross_track_match():
    talk = {"title": "Same Title", "track": "BioHacking Village"}
    vids = [{"track": "Car Hacking Village", "title": "Same Title", "url": "v1"}]
    assert _match_video(vids, talk) is None


def test_parse_people_filters_institutions_multilingual():
    speakers = parse_people(
        "Vincent Diemunsch, ANSSI, Université de Lorraine, CNRS, Inria, LORIA, Lucca Hirschi; Steve Kremer, LORIA"
    )
    names = [s["name"] for s in speakers]
    assert names == ["Vincent Diemunsch", "Lucca Hirschi", "Steve Kremer"]
    assert all("CNRS" not in (s["name"] + str(s["company"])) for s in speakers)


def test_parse_people_names_share_affiliation():
    speakers = parse_people("Cassidy Gibson and Daniel Olszewski, University of Florida")
    assert [s["name"] for s in speakers] == ["Cassidy Gibson", "Daniel Olszewski"]
    assert all(s["company"] == "University of Florida" for s in speakers)


def test_parse_people_drops_institution_only_block():
    speakers = parse_people("Ludwig Maximilians Universität, University of the Bundeswehr Munich")
    assert speakers == []


def test_parse_people_german_center_school_orgs():
    speakers = parse_people(
        "Jane Doe, CISPA Helmholtz Center for Information Security; John Roe, King's College London"
    )
    assert [s["name"] for s in speakers] == ["Jane Doe", "John Roe"]


def _write_capture(path, capture):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capture), encoding="utf-8")


def test_report_year_sort_prefers_newest(tmp_path):
    per_conf = {
        "offensivecon": {
            "ocon-2020": _capture(_records("offensivecon", "eu", 2020)),
            "ocon-2025": _capture(_records("offensivecon", "eu", 2025)),
        }
    }
    ds = build_dataset(per_conf)
    md, _ = build_report(per_conf, ds)
    assert md.index("ocon-2025") < md.index("ocon-2020")
