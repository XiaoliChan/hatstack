from crawler.confs.vb import parse_programme

VB_PAGE = """<html><body>
<ul>
<li><a href="/conference/vb2019/abstracts/vine-great-firewall/">A vine climbing over the Great Firewall</a>
    Lion Gu (Qi An Xin Threat Intelligence Center)</li>
<li><a href="/conference/vb2019/abstracts/industry-report-classroom-arrest/">From industry report to classroom arrest</a>
    11:30 - 12:00 Wednesday 2 October Marijn Schuurbiers (NHTCU)</li>
<li><a href="/conference/vb2006/abstracts/case-virus-x/">Case: Virus X</a> Mikko Hypponen</li>
<li><a href="/conference/vb2019/abstracts/vine-great-firewall/">A vine climbing over the Great Firewall</a></li>
</ul></body></html>"""


def test_vb_programme_extract():
    recs = parse_programme(2019, VB_PAGE)
    assert len(recs) == 3  # 4th anchor is a duplicate slug
    vine = next(r for r in recs if "vine" in r["title"])
    assert vine["speakers"][0]["name"] == "Lion Gu"
    assert vine["speakers"][0]["company"] == "Qi An Xin Threat Intelligence Center"
    arrest = next(r for r in recs if "classroom" in r["title"])
    assert arrest["speakers"][0]["name"] == "Marijn Schuurbiers"  # time noise stripped
    assert arrest["id"].startswith("vb19-")


def test_vb_wrong_page_guard():
    assert parse_programme(2019, "<html>no abstracts</html>") == []
