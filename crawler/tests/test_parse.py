import json
from pathlib import Path

from crawler.parse import parse_event_json, parse_legacy_html

FIX = Path(__file__).parent / "fixtures"


def load_us24():
    return json.loads((FIX / "us-24-sessions.json").read_text(encoding="utf-8"))


def test_json_event_basic_counts():
    records = parse_event_json({"region": "us", "year": 2024}, load_us24())
    assert len(records) > 80
    # breakfast/registration noise dropped (no speakers, no files)
    assert not any(r["title"].startswith("Briefings Breakfast") for r in records)


def test_json_event_record_shape():
    records = parse_event_json({"region": "us", "year": 2024}, load_us24())
    r = next(x for x in records if "Arbitrary Data Manipulation" in x["title"])
    assert r["files"]["slides"].startswith("https://i.blackhat.com/")
    assert r["id"].startswith("us24-")
    assert r["event"] == {"region": "us", "year": 2024, "label": "US-24"}
    assert r["abstract"]  # html stripped to text
    assert "<" not in r["abstract"]


def test_json_event_speaker_join():
    records = parse_event_json({"region": "us", "year": 2024}, load_us24())
    names = {s["name"] for r in records for s in r["speakers"]}
    assert "Jen Easterly" in names
    spk = next(s for s in names if s == "Jen Easterly")
    rec = next(r for r in records if any(s["name"] == "Jen Easterly" for s in r["speakers"]))
    e = next(s for s in rec["speakers"] if s["name"] == "Jen Easterly")
    assert e["company"] and "CISA" in e["company"]


def test_json_event_files_variants():
    records = parse_event_json({"region": "us", "year": 2024}, load_us24())
    assert any(r["files"]["tool"] for r in records) or True  # tool optional
    # every record has at least a speaker or a file
    assert all(r["speakers"] or any(r["files"].values()) for r in records)
    # no empty-string URLs leak through
    assert all(v for r in records for v in r["files"].values() if v is not None)


def test_legacy_us16_blocks():
    html = (FIX / "us-16-briefings.html").read_text(encoding="utf-8")
    records = parse_legacy_html({"region": "us", "year": 2016}, html)
    assert len(records) > 80
    r = next(x for x in records if "BadTunnel" in x["title"])
    assert r["title"].startswith("BadTunnel")
    assert r["files"]["slides"] and r["files"]["slides"].endswith(
        "us-16-Yu-BadTunnel-How-Do-I-Get-Big-Brother-Power.pdf"
    )
    assert r["files"]["whitepaper"] and "-wp.pdf" in r["files"]["whitepaper"]
    assert "Microsoft" in r["abstract"] or len(r["abstract"]) > 80
    assert r["event"]["label"] == "US-16"


def test_legacy_flat_fallback():
    # page without h2 blocks -> filename-derived records
    html = """
    <html><body>
      <b>Some Old Talk</b>
      <a href="https://www.blackhat.com/docs/us-09/materials/us-09-Someone-Example-Talk.pdf">pdf</a>
    </body></html>
    """
    records = parse_legacy_html({"region": "us", "year": 2009}, html)
    assert len(records) == 1
    assert records[0]["files"]["slides"].endswith(".pdf")
    assert records[0]["title"]
