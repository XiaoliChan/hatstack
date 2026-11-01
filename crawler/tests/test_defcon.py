from crawler.confs.defcon import _match_video, parse_filename
from crawler.dataset import build_records


def test_parse_presentations_format():
    r = parse_filename(
        "DEF CON 32 - Aaron Grattafiori Ivan Evtimov - Taming the Beast - Inside the Llama 3 Red Team Process.pdf",
        32,
    )
    assert r["title"] == "Taming the Beast - Inside the Llama 3 Red Team Process"
    assert "Grattafiori" in r["speakers_text"]
    assert r["track"] is None


def test_parse_village_format_and_typo():
    r = parse_filename(
        "DEF CON 32 - Adversary Vilage - Mauro Eldritch & Cybelle Oliveira - MFT - Malicious Fungible Tokens.pdf",
        32,
    )
    assert r["track"] == "Adversary Village"
    assert r["title"] == "MFT - Malicious Fungible Tokens"
    assert "Eldritch" in r["speakers_text"]


def test_parse_single_segment():
    r = parse_filename("DEF CON 12 - Something Weird and Wonderful.pdf", 12)
    assert r["title"] == "Something Weird and Wonderful"
    assert r["speakers_text"] == ""


def test_parse_ignores_non_pdf():
    assert parse_filename("DEF CON 32 - Aapo Oksman - demo.mp4", 32) is None


def test_video_match():
    talk = {"title": "MFT - Malicious Fungible Tokens", "track": "Adversary Village"}
    vids = [
        {"track": "Adversary Village",
         "title": "MFT - Malicious Fungible Tokens - Mauro Eldritch", "url": "u1"},
        {"track": None, "title": "MFT - Malicious Fungible Tokens", "url": "u2"},
    ]
    assert _match_video(vids, talk) == "u1"
    assert _match_video(vids, {"title": "Nope", "track": None}) is None


def test_records_kind_injects_conference():
    cap = {
        "status": "ok",
        "kind": "records",
        "records": [
            {
                "id": "dc32-x",
                "event": {"region": "us", "year": 2024, "label": "DC 32"},
                "title": "T",
                "speakers": [],
                "abstract": "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": None,
            }
        ],
        "meta": {},
    }
    out = build_records("dc-32", cap, conference="defcon")
    assert out[0]["conference"] == "defcon"
