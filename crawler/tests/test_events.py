from crawler.dataset import build_dataset, build_report
from crawler.events import (
    fallback_events,
    merge_candidates,
    normalize_region,
    parse_inventory,
    url_candidates,
)


def test_normalize_region():
    assert normalize_region("usa") == "us"
    assert normalize_region("europe") == "eu"
    assert normalize_region("europa") == "eu"
    assert normalize_region("japan") == "asia"
    assert normalize_region("sector") is None


def test_parse_inventory_patterns():
    html = """
    <a href="../archive/usa/2025/briefings/schedule/index.html">US 2025</a>
    <a href="/archive/europe/2023/briefings/schedule/index.html">EU 2023</a>
    <a href="/us-18/briefings/schedule/">US 18</a>
    <a href="/us-16/briefings.html">US 16</a>
    <a href="/asia-15/archives.html">Asia 15</a>
    <a href="/bh-usa-97/">USA 97</a>
    <a href="/archive/europe/2010/">EU 2010</a>
    <a href="/archive/sector/2024/briefings/schedule/index.html">skip me</a>
    <a href="https://www.blackhat.com/us-26/briefings/schedule/index.html">US 26</a>
    """
    inv = parse_inventory(html)
    # relative ../archive links resolve against the archives page
    assert "https://www.blackhat.com/archive/usa/2025/briefings/schedule/index.html" in inv["us-2025"]["urls"]
    assert inv["us-2025"]["kinds"][inv["us-2025"]["urls"][0]] == "json"
    assert "eu-2023" in inv
    assert "us-2018" in inv
    assert "us-2016" in inv and all(k == "legacy" for k in inv["us-2016"]["kinds"].values())
    assert "asia-2015" in inv
    assert "us-1997" in inv
    assert "eu-2010" in inv
    assert not any(k.startswith("sector") for k in inv)
    # JSON candidates sorted first when a year has both kinds
    both = parse_inventory('<a href="/us-16/briefings.html">a</a>'
                           '<a href="/us-16/briefings/schedule/">b</a>')
    assert both["us-2016"]["urls"][0].endswith("schedule/")


def test_url_candidates_order():
    # microsite first everywhere: /archive/ HTML navigations are hard-blocked
    assert url_candidates("us", 2024)[0].endswith("/us-24/briefings/schedule/index.html")
    assert url_candidates("us", 2018)[0].endswith("/us-18/briefings/schedule/index.html")
    assert url_candidates("asia", 2015)[0].endswith("/asia-15/briefings.html")
    assert url_candidates("eu", 2020)[0].endswith("/eu-20/briefings/schedule/index.html")
    assert url_candidates("eu", 2020)[1] == (
        "https://www.blackhat.com/archive/europe/2020/briefings/schedule/index.html"
    )


def test_merge_candidates_adds_microsites_to_archive_only_events():
    # archives.html links only the /archive/ path (hard-blocked for nav);
    # merge_candidates must inject the microsite URL BEFORE it
    inv = parse_inventory(
        '<a href="../archive/asia/2026/briefings/schedule/">asia 26</a>'
    )
    ev = inv["asia-2026"]
    assert ev["urls"] == ["https://www.blackhat.com/archive/asia/2026/briefings/schedule/"]
    merged = merge_candidates(inv)["asia-2026"]
    assert merged["urls"][0] == (
        "https://www.blackhat.com/asia-26/briefings/schedule/index.html"
    )
    assert "https://www.blackhat.com/archive/asia/2026/briefings/schedule/" in merged["urls"]


def test_fallback_events_coverage():
    ev = fallback_events()
    assert "us-2024" in ev and "eu-2013" in ev and "asia-2016" in ev
    assert "us-1997" in ev and "eu-2005" in ev and "asia-2006" in ev  # pre-2013 curated
    assert all(e["urls"] for e in ev.values())


def test_dataset_and_report():
    from crawler.parse import parse_event_json, parse_legacy_html
    import json
    from pathlib import Path

    fix = Path(__file__).parent / "fixtures"
    caps = {
        "us-2024": {
            "status": "ok",
            "kind": "json",
            "data": json.loads((fix / "us-24-sessions.json").read_text(encoding="utf-8")),
            "meta": {"url": "https://example/a", "title": "Black Hat USA 2024"},
        },
        "us-2016": {
            "status": "ok",
            "kind": "legacy",
            "html": (fix / "us-16-briefings.html").read_text(encoding="utf-8"),
            "meta": {"url": "https://example/b", "title": "Black Hat USA 2016"},
        },
        "eu-2020": {"status": "failed"},
    }
    ds = build_dataset({"blackhat": caps})
    ids = [s["id"] for s in ds["sessions"]]
    assert len(ids) == len(set(ids))  # deduped
    years = {s["event"]["year"] for s in ds["sessions"]}
    assert years == {2016, 2024}
    assert all(s["conference"] == "blackhat" for s in ds["sessions"])
    assert ds["conferences"] == ["blackhat"]
    # newest first
    assert ds["sessions"][0]["event"]["year"] == 2024

    md, rep = build_report({"blackhat": caps}, ds)
    assert "| blackhat/us-2024 | ok | json |" in md
    assert "| blackhat/eu-2020 | failed |" in md
    assert rep["events"]["blackhat/us-2016"]["sessions"] > 80
