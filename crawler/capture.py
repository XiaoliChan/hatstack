"""Playwright capture engine — the Phase 0 validated architecture.

One FRESH Chromium process per event; Cloudflare challenge auto-passes via
title-check + reload; JSON-era events are harvested by listening for the page's
OWN sessions.json XHR (our own in-page requests are blocked — see probe log).
"""
from __future__ import annotations

import json
import re
import random
import time

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
ARCHIVES_URL = "https://www.blackhat.com/html/archives.html"
CHALLENGE_MARKERS = ("just a moment", "attention required")


def _is_challenge(title: str) -> bool:
    t = (title or "").lower()
    return any(m in t for m in CHALLENGE_MARKERS)


def clear_challenge(page, url: str, tries: int = 4, settle: int = 8, log=None) -> bool:
    """goto + retry until the page is not a Cloudflare interstitial. Fast-fails on HTTP >= 400."""
    for i in range(tries):
        try:
            resp = page.goto(url, timeout=60000, wait_until="domcontentloaded")
        except Exception:
            resp = None
        status = resp.status if resp is not None else "?"
        if resp is not None and resp.status >= 400 and resp.status not in (403, 429, 503):
            if log:
                log(f"try {i}: HTTP {status}, not retryable")
            return False  # 404 and friends: no point retrying
        time.sleep(settle)
        title = page.title()
        if not _is_challenge(title):
            return True
        if log:
            log(f"try {i}: HTTP {status}, challenge title={title!r}")
        time.sleep(12)
    return False


def _new_page(pw):
    browser = pw.chromium.launch(args=["--no-sandbox"])
    ctx = browser.new_context(user_agent=UA)
    return browser, ctx, ctx.new_page()


def fetch_inventory(pw) -> str | None:
    """archives.html in its own fresh browser (first navigation passes)."""
    browser, _ctx, page = _new_page(pw)
    try:
        if clear_challenge(page, ARCHIVES_URL):
            return page.content()
    finally:
        browser.close()
    return None


def crawl_event(pw, event: dict, attempts: int = 3) -> dict:
    """Try each candidate URL in fresh browsers until valid data or failure.

    Returns {'status': 'ok'|'failed', 'kind': 'json'|'legacy', ...raw payload}.
    Verbose per-attempt output goes to stdout and into meta.trace for the report.
    """
    key = f"{event.get('region')}-{event.get('year')}"
    trace: list[str] = []

    def say(line: str):
        print(f"    {line}")
        trace.append(line)

    for attempt in range(1, attempts + 1):
        browser = None
        say(f"attempt {attempt}: fresh browser")
        try:
            browser, _ctx, page = _new_page(pw)
            for url in event["urls"]:
                kind = event["kinds"].get(url, "legacy")
                say(f"goto ({kind}) {url}")
                ok = clear_challenge(page, url, log=say)
                if not ok:
                    say(f"challenge/clear failed, title={page.title()!r}")
                    continue
                say(f"cleared, title={page.title()!r}")
                if kind == "json":
                    result = _capture_json(page, url, event["year"], log=say)
                else:
                    result = _capture_legacy(page, url, log=say)
                if result:
                    result.setdefault("meta", {})
                    result["meta"].update(
                        {"attempt": attempt, "url": url, "kind": kind,
                         "title": page.title(), "trace": trace}
                    )
                    return result
        except Exception as e:
            say(f"attempt {attempt} error: {e!r}")
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
        time.sleep(20 * attempt)
    say("all attempts exhausted")
    return {"status": "failed", "region": event["region"], "year": event["year"],
            "meta": {"source": "live", "trace": trace}}


def _capture_json(page, url: str, expected_year: int, log=None) -> dict | None:
    captured: list = []

    def on_response(resp):
        try:
            if "sessions.json" in resp.url:
                captured.append(resp)
        except Exception:
            pass

    page.on("response", on_response)
    try:
        time.sleep(12)  # page's own JS fetches sessions.json and renders
        rendered = page.locator("ul#cal_content_Day li").count()
        title = page.title()
        if log:
            log(f"rendered_li={rendered}, xhr_captured={len(captured)}, title={title!r}")
        for resp in captured:
            try:
                if log:
                    log(f"xhr {resp.status} {resp.url[-70:]}")
                if resp.status != 200:
                    continue
                data = json.loads(resp.body())
            except Exception:
                continue
            # year validation: guard against microsite redirects to the
            # current-year event (e.g. /eu-24/ -> Europe 2026)
            year_ok = f"/{expected_year}/" in resp.url or str(expected_year) in title
            if not year_ok and log:
                log(f"year validation failed (want {expected_year})")
            if year_ok and data:
                return {
                    "status": "ok",
                    "kind": "json",
                    "region": None,
                    "year": expected_year,
                    "data": data,
                    "rendered_li": rendered,
                    "captured_url": resp.url,
                }
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    # some years don't fetch sessions.json via XHR but the page still renders
    # the schedule from inline data — harvest the rendered DOM instead
    if rendered > 0:
        if log:
            log(f"falling back to rendered DOM ({rendered} rows)")
        return {
            "status": "ok",
            "kind": "rendered",
            "html": page.content(),
            "rendered_li": rendered,
            "year": expected_year,
        }
    return None


def _capture_legacy(page, url: str, log=None) -> dict | None:
    html = page.content()
    n_pdfs = html.lower().count(".pdf")
    if log:
        log(f"legacy page {len(html)}B, pdf refs {n_pdfs}")
    if ".pdf" not in html.lower():
        # 2013-2015 era: listing links per-talk detail pages; the slug parser
        # lives in wayback.py — reuse it on live HTML too
        from crawler.wayback import _records_from_detail_links

        m = re.search(r"blackhat\.com/(us|eu|asia)-(\d{2})", url)
        if m:
            region, yy = m.group(1), m.group(2)
            recs = _records_from_detail_links(html, region, 2000 + int(yy))
            if log:
                log(f"detail-slug records: {len(recs)}")
            if recs:
                return {"status": "ok", "kind": "records", "records": recs}
        return None
    return {"status": "ok", "kind": "legacy", "html": html, "source_url": url}


def pace(min_s: float = 30, max_s: float = 45):
    time.sleep(random.uniform(min_s, max_s))
