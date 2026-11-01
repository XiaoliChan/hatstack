"""Shared Playwright render helper for JS-shell sites (x33fcon, redteamvillage,
troopers, nullcon...). Plain render — no Cloudflare challenge loop needed;
challenged sites should use crawler.capture instead."""
from __future__ import annotations

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def rendered_html(pw, url: str, settle: float = 6.0, timeout: int = 60000) -> str | None:
    browser = None
    try:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        import time

        time.sleep(settle)
        return page.content()
    except Exception:
        return None
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
