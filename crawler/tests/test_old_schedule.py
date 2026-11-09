import pytest

from crawler.parse import parse_old_schedule, parse_us13_schedule

# 2003-2007 layout (pattern A): innermost talk cell with a textday* title <p>
# plus speaker anchors into speakers.html#<name>; wrapper tds nest whole-day
# grids and must not glob every talk into one record
PATTERN_A = """<html><body><table>
<tr><td colspan="7"><b>Day 1 &bull; July 27, 2005</b></td></tr>
<tr>
  <td>08:00 - 08:50</td>
  <td><p class="textwhite8">Break</p></td>
</tr>
<tr>
  <td>09:00 - 09:50</td>
  <td><p class="textday2track1">World Exclusive &#150; Announcing the OWASP Guide 2.0</p>
      <p class="textred8"><a title="Andrew van der Stock" href="bh-usa-05-speakers.html#stock">Andrew van der Stock</a></p></td>
  <td><p class="textday2track4">Hacking VoIP Exposed</p>
      <p class="textday2track4"><a href="bh-usa-05-speakers.html#Endler">David Endler &amp; Mark Collier</a></p></td>
</tr>
<tr>
  <td>10:00 - 11:00</td>
  <td><p class="textday1track4">CISO Q&amp;A Panel</p>
      <p><a href="bh-usa-05-speakers.html#Moss">Scott Blake, Pamela Fusco, Andre Gold, Ken Pfost</a></p></td>
</tr>
</table></body></html>"""

# 2008-2009 layout (pattern B): div panels; the anchor carries the TITLE and
# the speaker sits in a trailing <span> after " - "
PATTERN_B = """<html><body>
<div class="evenbox_panel"><h5>09:00 - 10:15</h5>
  <h5><a href="bh-eu-09-speakers.html#Erroll">Privacy Protecting People or People Protecting Privacy</a> -
      <span style="color:white;">Lord Erroll</span></h5></div>
<div class="oddbox_panel"><h5>10:15 - 10:30</h5><h5>Break<br/></h5></div>
<div class="evenbox_panel"><h5>10:30 - 11:45</h5>
  <h5><a href="bh-eu-09-speakers.html#Nunez">SAP Penetration Testing</a> -
      <span>Chema Alonso &amp; Martin Vigo</span></h5></div>
</body></html>"""


@pytest.mark.parametrize(
    "html,region,year,want_talks",
    [
        (PATTERN_A, "us", 2005, 3),
        (PATTERN_B, "eu", 2009, 2),
        ("<html><body>no anchors here</body></html>", "us", 2005, 0),
    ],
)
def test_old_schedule_counts(html, region, year, want_talks):
    recs = parse_old_schedule({"region": region, "year": year, "source_url": "x"}, html)
    assert len(recs) == want_talks


def test_old_schedule_pattern_a_fields():
    recs = parse_old_schedule({"region": "us", "year": 2005, "source_url": "x"}, PATTERN_A)
    by_title = {r["title"]: r for r in recs}
    owasp = by_title["World Exclusive – Announcing the OWASP Guide 2.0"]
    assert owasp["speakers"] == [{"name": "Andrew van der Stock", "company": None, "role": None}]
    voip = by_title["Hacking VoIP Exposed"]
    assert [s["name"] for s in voip["speakers"]] == ["David Endler", "Mark Collier"]
    assert owasp["id"].startswith("us05-") and owasp["event"]["year"] == 2005


def test_old_schedule_pattern_b_fields():
    recs = parse_old_schedule({"region": "eu", "year": 2009, "source_url": "x"}, PATTERN_B)
    sap = next(r for r in recs if "SAP" in r["title"])
    assert [s["name"] for s in sap["speakers"]] == ["Chema Alonso", "Martin Vigo"]
    erroll = next(r for r in recs if "Privacy" in r["title"])
    assert [s["name"] for s in erroll["speakers"]] == ["Lord Erroll"]


def test_old_schedule_breaks_filtered():
    recs = parse_old_schedule({"region": "us", "year": 2005, "source_url": "x"}, PATTERN_A)
    assert not any(r["title"].lower().startswith("break") for r in recs)


US13_DAY = """<html><body>
<div class="schedule-time"><h3>0900</h3></div>
<div class="schedule-info"><h3 class="schedule-info-description">
  <a href="../briefings.html#Alexander" class="schedule-briefing-title">Keynote Speaker: General Keith B. Alexander</a></h3></div>
<div class="schedule-tracks"><div class="schedule-track-col"><div class="schedule-track">
  <a href="../briefings.html#Young" class="schedule-briefing-title">Mainframes: The Past Will Come to <span class="more-briefing-title">Haunt You</span></a>
  <a href="../speakers/Philip-Young.html" class="schedule-briefing-speaker">Philip Young</a> &amp;
  <a href="../speakers/Chick.html" class="schedule-briefing-speaker">Colin Chick</a>
  <br><span class="schedule-briefing-room">Room 310</span>
</div></div></div>
</body></html>"""


def test_us13_schedule_extracts_title_and_speakers():
    recs = parse_us13_schedule({"region": "us", "year": 2013, "source_url": "x"}, US13_DAY)
    assert len(recs) == 2
    main = next(r for r in recs if "Mainframes" in r["title"])
    # title continues inside the nested span and must be joined
    assert main["title"] == "Mainframes: The Past Will Come to Haunt You"
    assert [s["name"] for s in main["speakers"]] == ["Philip Young", "Colin Chick"]
    assert main["id"].startswith("us13-")


def test_us13_schedule_wrong_page_guard():
    assert parse_us13_schedule({"region": "us", "year": 2013}, "<html>other era</html>") == []
