"""Pure parsers: blackhat.com sessions.json -> records; legacy HTML -> records.

No network, no Playwright. Everything here is unit-testable against fixtures.
"""
from __future__ import annotations

import re
from bs4 import BeautifulSoup

REGION_LABEL = {"us": "US", "eu": "EU", "asia": "Asia"}


def event_label(region: str, year: int) -> str:
    return f"{REGION_LABEL[region]}-{str(year)[2:]}"


def strip_html(text) -> str:
    if not text:
        return ""
    return BeautifulSoup(str(text), "lxml").get_text(" ", strip=True)


def _norm_file_url(url) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url or url.lower() in ("n/a", "tbd"):
        return None
    if url.startswith("http://i.blackhat.com"):
        url = "https://i.blackhat.com" + url[len("http://i.blackhat.com"):]
    return url


def _extract_files(bh_files) -> dict:
    """bh_files is {} / [] / {slides:{label,url}, whitepaper:{...}, source_code:{...}}."""
    files = {"slides": None, "whitepaper": None, "tool": None}
    if not isinstance(bh_files, dict):
        return files
    mapping = {"slides": "slides", "whitepaper": "whitepaper", "source_code": "tool"}
    for key, out in mapping.items():
        entry = bh_files.get(key)
        if isinstance(entry, dict):
            files[out] = _norm_file_url(entry.get("url"))
    return files


def _join_speakers(session_speakers, speakers_db: dict) -> list[dict]:
    # normalize keys to strings: JSON round-trips dict keys as str, sessions
    # reference person_id as int
    db = {str(k): v for k, v in (speakers_db or {}).items() if isinstance(v, dict)}
    out = []
    for s in session_speakers or []:
        if not isinstance(s, dict) or s.get("person_id") is None:
            continue
        info = db.get(str(s.get("person_id")), {})
        name = " ".join(
            x for x in (strip_html(info.get("first_name")), strip_html(info.get("last_name"))) if x
        )
        if not name:
            continue
        out.append(
            {
                "name": name,
                "company": strip_html(info.get("company")) or None,
                "role": strip_html(info.get("role")) or strip_html(s.get("role")) or None,
            }
        )
    return out


def parse_event_json(event: dict, data: dict) -> list[dict]:
    """event: {'region','year'}; data: parsed sessions.json (dict with sessions+speakers)."""
    label = event_label(event["region"], event["year"])
    speakers_db = data.get("speakers") or {}
    if isinstance(speakers_db, list):
        speakers_db = {s.get("person_id"): s for s in speakers_db if isinstance(s, dict)}
    sessions = data.get("sessions") or {}
    if isinstance(sessions, list):
        sessions = {s.get("id"): s for s in sessions if isinstance(s, dict)}

    records = []
    for sid, s in sessions.items():
        if not isinstance(s, dict):
            continue
        if str(s.get("type", "")).lower() not in ("briefings", "briefing"):
            continue
        if str(s.get("cancelled") or "0") not in ("0", "", "None"):
            continue
        files = _extract_files(s.get("bh_files"))
        speakers = _join_speakers(s.get("speakers"), speakers_db)
        if not any(files.values()) and not speakers:
            continue  # breakfast / registration / lounge noise
        abstract = strip_html(s.get("description")) or strip_html(s.get("marketing_description"))
        records.append(
            {
                "id": f"{label.lower().replace('-', '')}-{sid}",
                "event": {"region": event["region"], "year": event["year"], "label": label},
                "title": strip_html(s.get("title")) or f"(untitled {sid})",
                "speakers": speakers,
                "abstract": abstract,
                "track": strip_html(s.get("track_1")) or None,
                "files": files,
                "video_url": None,
                "source_url": event.get("source_url"),
            }
        )
    return records


_FILENAME_TITLE_RE = re.compile(r"^[a-z]{2}-\d{2}-(.+)$")


def _title_from_filename(url: str) -> str:
    name = url.rsplit("/", 1)[-1]
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    m = _FILENAME_TITLE_RE.match(name)
    if m:
        name = m.group(1)
    # first token before the title usually is the author surname; drop one token
    parts = name.split("-")
    if len(parts) > 1:
        parts = parts[1:]
    text = " ".join(parts)
    return re.sub(r"\s+", " ", text).strip(" .-")


def _classify_legacy_anchor(a) -> str | None:
    """'slides' | 'whitepaper' | None for a legacy PDF anchor."""
    href = (a.get("href") or "").lower()
    if not href.endswith(".pdf"):
        return None
    img = a.find("img")
    title = (img.get("title") or "").lower() if img else ""
    if "white" in title:
        return "whitepaper"
    if "presentation" in title or "slide" in title:
        return "slides"
    if "-wp" in href.rsplit("/", 1)[-1]:
        return "whitepaper"
    return "slides"


def parse_legacy_html(event: dict, html: str) -> list[dict]:
    """Legacy (<=2017) briefings pages: h2 title -> p abstract -> link-icon anchors -> 'presented by'."""
    label = event_label(event["region"], event["year"])
    soup = BeautifulSoup(html, "lxml")
    records = []

    for h in soup.find_all("h2"):
        title = h.get_text(" ", strip=True)
        if not title or len(title) < 8:
            continue
        block: list = []
        speakers_text = ""
        mode = "main"
        for sib in h.find_next_siblings():
            if not getattr(sib, "name", None):
                continue  # skip NavigableStrings/comments
            if sib.name in ("h1", "h2"):
                break
            if sib.name in ("h3", "h4"):
                if "presented by" in sib.get_text(" ", strip=True).lower():
                    mode = "speakers"
                    continue
                break
            if mode == "speakers":
                speakers_text += " " + sib.get_text(" ", strip=True)
            else:
                block.append(sib)

        files = {"slides": None, "whitepaper": None, "tool": None}
        abstract = ""
        for el in block:
            for a in el.find_all("a") if el.name != "a" else [el]:
                kind = _classify_legacy_anchor(a)
                if kind and not files[kind]:
                    files[kind] = _norm_file_url(a.get("href"))
            if el.name == "p" and not abstract and len(el.get_text(strip=True)) > 80:
                abstract = el.get_text(" ", strip=True)

        if not any(files.values()):
            continue

        speakers = []
        for chunk in re.split(r"[,;\n]+| and ", speakers_text):
            name = chunk.strip(" .-–")
            if 2 < len(name) < 60 and not any(d in name for d in ("http", "@", "www")):
                speakers.append({"name": name, "company": None, "role": None})

        records.append(
            {
                "id": f"{label.lower().replace('-', '')}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]}",
                "event": {"region": event["region"], "year": event["year"], "label": label},
                "title": title,
                "speakers": speakers[:6],
                "abstract": abstract[:4000],
                "track": None,
                "files": files,
                "video_url": None,
                "source_url": event.get("source_url"),
            }
        )

    # Flat fallback for years without h2 blocks: one record per slides-anchor.
    if len(records) < 5:
        records = []
        for a in soup.find_all("a", href=lambda h: h and h.lower().endswith(".pdf")):
            kind = _classify_legacy_anchor(a)
            if kind != "slides":
                continue
            url = _norm_file_url(a.get("href"))
            heading = a.find_previous(["h1", "h2", "h3", "h4", "b", "strong"])
            title = heading.get_text(" ", strip=True) if heading else ""
            if not title or len(title) < 8 or title.lower() == "presented by":
                title = _title_from_filename(url or "")
            records.append(
                {
                    "id": f"{label.lower().replace('-', '')}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]}",
                    "event": {"region": event["region"], "year": event["year"], "label": label},
                    "title": title,
                    "speakers": [],
                    "abstract": "",
                    "track": None,
                    "files": {"slides": url, "whitepaper": None, "tool": None},
                    "video_url": None,
                    "source_url": event.get("source_url"),
                }
            )
    return records


_NON_PERSON = re.compile(
    r"president|officer|\bceo\b|\bcio\b|\bciso\b|director|founder|manager|chief\b"
    r"|inc\b|corp|llc|ltd|gmbh|labs?|technolog|security|solutions|university"
    r"|in-?q-?tel|department|\bagent|special|professional|evangelist|architect"
    r"|researcher|consultant|engineer|analyst|trainer|instructor|professor",
    re.I,
)


def _person_candidates(txt: str) -> list[dict]:
    """Split an anchor/label text into person-name dicts; comma chunks that
    look like job titles or orgs are dropped (old pages embed
    'Name, President and CEO, In-Q-Tel' in speaker anchors)."""
    out: list[dict] = []
    for chunk in re.split(r"\s*&\s*|,|;|\s+and\s+", txt):
        chunk = chunk.strip(" .")
        words = chunk.split()
        if not (2 < len(chunk) < 40) or not (1 <= len(words) <= 4) or any(ch.isdigit() for ch in chunk):
            continue
        if _NON_PERSON.search(chunk) and len(words) > 1:
            continue
        out.append({"name": chunk, "company": None, "role": None})
    return out


def parse_old_schedule(event: dict, html: str) -> list[dict]:
    """2003-2009 schedule pages. Two layouts:
    A) 2003-2007 nested tables — innermost talk cells pair a title <p>
       (textday*-classed) with speaker anchors into *speakers.html#<name>;
    B) 2008-2009 div panels — the anchor itself carries the talk title and
       the speaker sits in a trailing <span>/plain text after " - ".
    Returns [] when the page has no speakers.html# anchors (wrong-page
    guard, e.g. pre-conference placeholder snapshots)."""
    if "speakers.html#" not in html:
        return []
    region, year = event["region"], event["year"]
    label = event_label(region, year)
    soup = BeautifulSoup(html, "html.parser")
    anchor_re = re.compile(r"speakers\.html#")
    records: list[dict] = []
    seen: set[str] = set()

    def _push(title: str, speakers: list[dict], src: str) -> None:
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 8 or re.search(
            r"\bbreak\b|lunch|registration|reception|\bparty\b|sponsored by|location & times",
            title,
            re.I,
        ):
            return
        key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if not key or key in seen:
            return
        seen.add(key)
        records.append(
            {
                "id": f"{region}{year % 100:02d}-{key[:60]}",
                "event": {"region": region, "year": year, "label": label},
                "title": title,
                "speakers": speakers[:5],
                "abstract": "",
                "track": None,
                "files": {"slides": None, "whitepaper": None, "tool": None},
                "video_url": None,
                "source_url": event.get("source_url"),
            }
        )

    # Pattern A — innermost tds only; wrapper tds (whole-day grids) contain
    # nested tds and would glob every talk of the day into one record
    for td in soup.find_all("td"):
        if td.find_all("td"):
            continue
        anchors = td.find_all("a", href=anchor_re)
        if not anchors:
            continue
        title = ""
        for p in td.find_all("p"):
            if p.find("a"):
                continue
            t = p.get_text(" ", strip=True)
            if len(t) > len(title) and not t[:1].isdigit() and len(t) >= 8:
                title = t
        if not title:
            continue
        speakers: list[dict] = []
        for a in anchors:
            speakers.extend(_person_candidates(a.get_text(" ", strip=True)))
        dedup = {s["name"]: s for s in speakers}
        _push(title, list(dedup.values()), str(td)[:60])

    # Pattern B — h-heading/list panels where the anchor is the title
    for h in soup.find_all(["h5", "h4", "h3", "li"]):
        a = h.find("a", href=anchor_re)
        if a is None:
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 8 or title[:1].isdigit():
            continue
        speaker_txt = ""
        for sp in h.find_all("span"):
            t = sp.get_text(" ", strip=True)
            if t and t.lower() != title.lower() and len(t) < 80:
                speaker_txt += ", " + t
        if not speaker_txt:
            m = re.search(r"-\s*([^–-]{3,80})$", h.get_text(" ", strip=True))
            speaker_txt = m.group(1) if m else ""
        _push(title, _person_candidates(speaker_txt), str(h)[:60])

    return records


def parse_rendered_schedule(event: dict, html: str) -> list[dict]:
    """Rendered Black Hat schedule DOM (no-XHR years): li rows under
    ul#cal_content_Day carry title/speakers; detail modals (when present)
    carry abstract + material links.

    html.parser (not lxml): crawler-harvested modal blocks appended after a
    JS-rendered DOM contain mis-nested tags that lxml silently truncates —
    observed losing all 124 harvested modals; html.parser keeps them."""
    label = event_label(event["region"], event["year"])
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen: set[str] = set()
    # structured rows first (itemprop-rich schedule markup)
    for row in soup.select("li.cal_row_content, [id^=cal_session_]"):
        link = row.select_one("[itemprop=summary] a") or row.find("a", href=re.compile("#"))
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        if not title or len(title) < 6:
            continue
        if re.search(r"breakfast|lunch|break\b|registration|reception|party|coffee|happy hour", title, re.I):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        speakers = []
        for sp in row.select("[itemprop=performers]"):
            txt = sp.get_text(" ", strip=True)
            txt = re.sub(r"^(Speaker[s]?|Contributor[s]?)\s*:?\s*", "", txt, flags=re.I)
            txt = re.sub(r"\bContributor[s]?\s*:\s*", "", txt)
            txt = re.sub(r"Location\s*:.*$", "", txt)
            for name in re.split(r"[,;·]|\s{2,}|\s+and\s+", txt):
                name = name.strip(" ,;·")
                if 3 < len(name) < 50 and not re.search(r"\d|TBD|Speaker", name, re.I):
                    speakers.append({"name": name, "company": None, "role": None})
        # detail modal harvested by the crawler is keyed cal_detail_<data-id>
        data_id = link.get("data-id")
        scope = None
        if data_id:
            scope = soup.find(id=f"cal_detail_{data_id}")
        if scope is None:
            anchor = (link.get("href") or "").lstrip("#")
            scope = soup.find(id=re.compile(re.escape(anchor))) if anchor else None
        scope = scope or row
        files = {"slides": None, "whitepaper": None, "tool": None}
        for a2 in scope.find_all("a", href=True):
            h = a2["href"]
            label_txt = a2.get_text(" ", strip=True).lower()
            is_slide_link = h.lower().endswith(".pdf") or "speakerdeck" in h or "slideshare" in h or "slide" in label_txt
            if is_slide_link:
                if "-wp" in h.rsplit("/", 1)[-1] and not files["whitepaper"]:
                    files["whitepaper"] = _norm_file_url(h)
                elif not files["slides"]:
                    files["slides"] = _norm_file_url(h)
        desc = scope.find(class_=re.compile("desc|abstract|session-detail", re.I))
        records.append(
            {
                "id": f"{label.lower().replace('-', '')}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]}",
                "event": {"region": event["region"], "year": event["year"], "label": label},
                "title": title,
                "speakers": speakers[:5],
                "abstract": desc.get_text(" ", strip=True)[:4000] if desc else "",
                "track": None,
                "files": files,
                "video_url": None,
                "source_url": event.get("source_url"),
            }
        )
    if records:
        return records
    # us-26 style: itemprop=summary links outside cal_content_Day; detail
    # sections keyed by session id render below (or after clicking)
    for a in soup.select("[itemprop=summary] a[data-id], a.sd_link[data-id]"):
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 6:
            continue
        data_id = a.get("data-id")
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        row = a.find_parent("div") or a
        speakers = []
        perf = row.find("[itemprop=performers]") if row else None
        if perf is None:
            # siblings of the row div share the performers block
            parent = a.parent
            perf = parent and parent.find_next("[itemprop=performers]")
        if perf:
            txt = perf.get_text(" ", strip=True)
            txt = re.sub(r"(Speaker|Contributor)s?\s*:?\s*", "", txt, flags=re.I)
            txt = re.sub(r"Location\s*:.*$", "", txt)
            for name in re.split(r"[,;·]|\s{2,}", txt):
                name = re.sub(r"^(Speaker|Contributor)s?\s*:\s*", "", name.strip(), flags=re.I)
                name = name.strip()
                if 3 < len(name) < 50 and not re.search(r"TBD|Tracks|Format", name, re.I):
                    speakers.append({"name": name, "company": None, "role": None})
        files = {"slides": None, "whitepaper": None, "tool": None}
        abstract = ""
        detail = soup.find(id=f"cal_detail_{data_id}") if data_id else None
        if detail is None and data_id:
            detail = soup.find(id=re.compile(re.escape(data_id)))
        if detail:
            for a2 in detail.find_all("a", href=True):
                h = a2["href"]
                if h.lower().endswith(".pdf"):
                    if "-wp" in h.rsplit("/", 1)[-1] and not files["whitepaper"]:
                        files["whitepaper"] = _norm_file_url(h)
                    elif not files["slides"]:
                        files["slides"] = _norm_file_url(h)
                elif not files["slides"] and "slide" in (a2.get_text(" ", strip=True).lower() + h.lower()):
                    files["slides"] = _norm_file_url(h)
            desc = detail.find(class_=re.compile("desc|abstract", re.I))
            if desc:
                abstract = desc.get_text(" ", strip=True)[:4000]
        label = event_label(event["region"], event["year"])
        records.append(
            {
                "id": f"{label.lower().replace('-', '')}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]}",
                "event": {"region": event["region"], "year": event["year"], "label": label},
                "title": title,
                "speakers": speakers[:5],
                "abstract": abstract,
                "track": None,
                "files": files,
                "video_url": None,
                "source_url": event.get("source_url"),
            }
        )
    for li in soup.select("ul#cal_content_Day li"):
        a = li.find("a", attrs={"href": re.compile("#")})
        if not a:
            continue
        title_el = a.find(["h3", "h4", "strong", "b"]) or a
        title = title_el.get_text(" ", strip=True)
        if not title or len(title) < 6:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        # speakers: the rest of the row text minus the title
        row_text = li.get_text(" ", strip=True).replace(title, " ", 1)
        row_text = re.sub(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", " ", row_text)
        speakers = [
            {"name": s.strip(), "company": None, "role": None}
            for s in re.split(r"\s{2,}|,|·", row_text)
            if 3 < len(s.strip()) < 40 and not re.search(r"\d", s)
        ][:5]
        # detail modal for this session (id-matched) if rendered
        files = {"slides": None, "whitepaper": None, "tool": None}
        abstract = ""
        anchor = (a.get("href") or "").lstrip("#")
        detail = soup.find(id=re.compile(re.escape(anchor))) if anchor else None
        scope = detail if detail else li
        for link in scope.find_all("a", href=True):
            href = link["href"]
            if href.lower().endswith(".pdf"):
                if "-wp" in href.rsplit("/", 1)[-1] and not files["whitepaper"]:
                    files["whitepaper"] = _norm_file_url(href)
                elif not files["slides"]:
                    files["slides"] = _norm_file_url(href)
            elif "i.blackhat.com" in href and not files["slides"]:
                files["slides"] = _norm_file_url(href)
        desc = scope.find(class_=re.compile("desc|abstract|session-detail", re.I))
        if desc:
            abstract = desc.get_text(" ", strip=True)[:4000]
        records.append(
            {
                "id": f"{label.lower().replace('-', '')}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]}",
                "event": {"region": event["region"], "year": event["year"], "label": label},
                "title": title,
                "speakers": speakers,
                "abstract": abstract,
                "track": None,
                "files": files,
                "video_url": None,
                "source_url": event.get("source_url"),
            }
        )
    return records
