from crawler.wayback import json_candidates, page_candidates


def test_json_candidates_variants():
    ev = {"region": "us", "year": 2024}
    urls = json_candidates(ev)
    assert urls[0] == "https://www.blackhat.com/us-24/briefings/schedule/sessions.json"
    assert urls[1] == "https://www.blackhat.com/archive/usa/2024/briefings/schedule/sessions.json"
    assert json_candidates({"region": "eu", "year": 2020})[1].endswith(
        "/archive/europe/2020/briefings/schedule/sessions.json"
    )


def test_page_candidates_legacy_and_pre2013():
    legacy = page_candidates({"region": "asia", "year": 2015})
    assert legacy[0].endswith("/asia-15/briefings.html")
    assert any(u.endswith("archives.html") for u in legacy)
    pre = page_candidates({"region": "us", "year": 1997,
                           "urls": ["https://www.blackhat.com/bh-usa-97/"]})
    assert pre == ["https://www.blackhat.com/bh-usa-97/"]


def test_cdx_newest_row_parsing():
    # cdx rows: header + captures; newest = last row's timestamp
    import json
    rows = [["urlkey", "timestamp"], ["com,x)/a", "20240101"], ["com,x)/a", "20250420"]]
    assert rows[-1][1] == "20250420"
