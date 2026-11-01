"""Event inventory: which BlackHat events exist and which URLs to try for each.

Mainline regions only (us/eu/asia), all years. Recent years are JSON-era
(schedule page fetches sessions.json); <=2017 are static HTML pages.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ARCHIVES_BASE = "https://www.blackhat.com/html/archives.html"

LONG_REGION = {"us": "usa", "eu": "europe", "asia": "asia"}


def normalize_region(tok: str) -> str | None:
    t = (tok or "").lower()
    if t in ("us", "usa"):
        return "us"
    if t in ("eu", "europe", "europa"):
        return "eu"
    if t in ("asia", "japan"):
        return "asia"
    return None


def _yy(y2: int, now: int = 26) -> int:
    return 2000 + y2 if y2 <= now else 1900 + y2


_PATTERNS = [
    # /archive/<region>/<year>/briefings/schedule/  (JSON era)
    (re.compile(r"/archive/(usa|europe|asia)/(\d{4})/briefings/schedule/?"), "json"),
    # /<rgn>-<yy>/briefings/schedule/  (JSON era microsites: us-18, us-26, ...)
    (re.compile(r"(?:^|blackhat\.com)/(us|eu|asia)-(\d{2})/briefings/schedule/?"), "json"),
    # /<rgn>-<yy>/briefings.html or archives.html  (legacy)
    (re.compile(r"(?:^|blackhat\.com)/(us|eu|asia)-(\d{2})/(?:briefings|archives)\.html"), "legacy"),
    # pre-2013: /bh-usa-97/ /bh-us-10/ /bh-eu-08/ /bh-asia-04/ /bh-japan-06/ etc.
    (re.compile(r"/bh-(usa|us|eu|europa|europe|asia|japan)-(\d{2,4})/?"), "legacy"),
    # /archive/europe/<year>/ static pages
    (re.compile(r"/archive/europe/(\d{4})/"), "legacy"),
]


def _year_from_token(tok: str) -> int | None:
    tok = tok.lstrip("0") or "0"
    if not tok.isdigit():
        return None
    n = int(tok)
    if n <= 26:
        return 2000 + n
    if 97 <= n <= 99:
        return 1900 + n
    if 1997 <= n <= 2012:
        return n
    return None


def parse_inventory(html: str) -> dict[str, dict]:
    """archives.html -> {event_key: {'region','year','urls':[...], 'kind_by_url':{url:kind}}}."""
    soup = BeautifulSoup(html, "lxml")
    events: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for rx, kind in _PATTERNS:
            m = rx.search(href)
            if not m:
                continue
            if len(m.groups()) == 2 and m.group(2).isdigit() and len(m.group(2)) == 4:
                region, year = normalize_region(m.group(1)), int(m.group(2))
            elif len(m.groups()) == 2 and "/" not in m.group(1):
                region, year = normalize_region(m.group(1)), _year_from_token(m.group(2))
            else:  # /archive/europe/<year>/ pattern has region embedded
                region, year = "eu", int(m.group(1))
            if not region or not year or year < 1997:
                continue
            url = urljoin(ARCHIVES_BASE, href).split("#")[0]
            key = f"{region}-{year}"
            ev = events.setdefault(
                key, {"region": region, "year": year, "urls": [], "kinds": {}}
            )
            if url not in ev["urls"]:
                ev["urls"].append(url)
                ev["kinds"][url] = kind
            break
    # within JSON-era, microsite paths first: /archive/ HTML navigations are
    # hard-blocked by Cloudflare even in fresh browsers (probe + smoke evidence)
    for ev in events.values():
        ev["urls"].sort(
            key=lambda u: (0 if (ev["kinds"][u] == "json" and "/archive/" not in u)
                           else 1 if ev["kinds"][u] == "json" else 2)
        )
    return events


def url_candidates(region: str, year: int) -> list[str]:
    """Ordered candidate URLs for one event. Microsite paths first — Cloudflare
    hard-blocks /archive/ HTML navigations; microsites pass the challenge."""
    long_r, yy = LONG_REGION[region], str(year)[2:]
    micro = f"https://www.blackhat.com/{region}-{yy}/briefings/schedule/index.html"
    arch = f"https://www.blackhat.com/archive/{long_r}/{year}/briefings/schedule/index.html"
    if year >= 2018:
        return [micro, arch]
    legacy = [
        f"https://www.blackhat.com/{region}-{yy}/briefings.html",
        f"https://www.blackhat.com/{region}-{yy}/archives.html",
    ]
    return legacy


def fallback_events() -> dict[str, dict]:
    """Generative mainline map when archives.html is unreachable."""
    events: dict[str, dict] = {}
    for year in range(2013, 2027):
        for region in ("us", "eu", "asia"):
            if region == "asia" and year == 2026:
                continue  # asia-26 not yet listed; will come from inventory
            urls = url_candidates(region, year)
            events[f"{region}-{year}"] = {
                "region": region,
                "year": year,
                "urls": urls,
                "kinds": {u: ("json" if u.endswith("schedule/index.html") else "legacy") for u in urls},
            }
    # pre-2013 curated mainline (paths as linked from archives.html)
    pre2013 = [
        ("us", 1997, "https://www.blackhat.com/bh-usa-97/"),
        ("us", 1998, "https://www.blackhat.com/bh-usa-98/"),
        ("us", 1999, "https://www.blackhat.com/bh-usa-99/"),
        ("us", 2008, "https://www.blackhat.com/bh-usa-08/"),
        ("us", 2009, "https://www.blackhat.com/bh-usa-09/"),
        ("us", 2010, "https://www.blackhat.com/bh-us-10/"),
        ("us", 2011, "https://www.blackhat.com/bh-us-11/"),
        ("us", 2012, "https://www.blackhat.com/bh-us-12/"),
    ]
    for year in range(2000, 2013):
        pre2013.append(("eu", year, f"https://www.blackhat.com/archive/europe/{year}/"))
    for year in range(2000, 2005):
        pre2013.append(("asia", year, f"https://www.blackhat.com/bh-asia-{year:02d}/"))
    for year in range(2005, 2009):
        pre2013.append(("asia", year, f"https://www.blackhat.com/bh-japan-{year:02d}/"))
    for region, year, url in pre2013:
        key = f"{region}-{year}"
        if key in events:
            continue
        events[key] = {"region": region, "year": year, "urls": [url], "kinds": {url: "legacy"}}
    return events
