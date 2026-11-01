"""Playwright capture engine — the Phase 0 validated architecture.

One FRESH Chromium process per event; Cloudflare challenge auto-passes via
title-check + reload; JSON-era events are harvested by listening for the page's
OWN sessions.json XHR (our own in-page requests are blocked — see probe log).
"""
from __future__ import annotations

import json
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


def clear_challenge(page, url: str, tries: int = 4, settle: int = 8) -> bool:
    """goto + retry until the page is not a Cloudflare interstitial. Fast-fails on HTTP >= 400."""
    for i in range(tries):
        try:
            resp = page.goto(url, timeout=60000, wait_until="domcontentloaded")
        except Exception:
            resp = None
        if resp is not None and resp.status >= 400 and resp.status not in (403, 429, 503):
            return False  # 404 and friends: no point retrying
        time.sleep(settle)
        if not _is_challenge(page.title()):
            return True
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
    """
    for attempt in range(1, attempts + 1):
        browser = None
        try:
            browser, _ctx, page = _new_page(pw)
            for url in event["urls"]:
                kind = event["kinds"].get(url, "legacy")
                if not clear_challenge(page, url):
                    continue
                if kind == "json":
                    result = _capture_json(page, url, event["year"])
                else:
                    result = _capture_legacy(page, url)
                if result:
                    result.setdefault("meta", {})
                    result["meta"].update(
                        {"attempt": attempt, "url": url, "kind": kind, "title": page.title()}
                    )
                    return result
        except Exception as e:
            print(f"[{event.get('region')}-{event.get('year')}] attempt {attempt} error: {e!r}")
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
        time.sleep(20 * attempt)
    return {"status": "failed", "region": event["region"], "year": event["year"]}


def _capture_json(page, url: str, expected_year: int) -> dict | None:
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
        for resp in captured:
            try:
                if resp.status != 200:
                    continue
                data = json.loads(resp.body())
            except Exception:
                continue
            # year validation: guard against microsite redirects to the
            # current-year event (e.g. /eu-24/ -> Europe 2026)
            year_ok = f"/{expected_year}/" in resp.url or str(expected_year) in title
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
    return None


def _capture_legacy(page, url: str) -> dict | None:
    html = page.content()
    if ".pdf" not in html.lower():
        return None
    return {"status": "ok", "kind": "legacy", "html": html, "source_url": url}


def pace(min_s: float = 30, max_s: float = 45):
    time.sleep(random.uniform(min_s, max_s))
