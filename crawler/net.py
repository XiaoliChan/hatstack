"""Shared subprocess-curl GET: several conference CDNs reject urllib3's TLS
fingerprint while plain curl passes. Runners ship curl."""
from __future__ import annotations

import subprocess


def curl_get(url: str, timeout: int = 60) -> tuple[int, str]:
    p = subprocess.run(
        ["curl", "-4", "-sSL", "--max-time", str(timeout),
         "-A", "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0.0.0 Safari/537.36",
         "-w", "\n%{http_code}", url],
        capture_output=True, timeout=timeout + 30,
    )
    # decode manually: CI runners use a POSIX locale where text=True explodes
    # on non-ASCII bytes (speaker names) — this killed SEC-T and DeepSec runs
    stdout = p.stdout.decode("utf-8", errors="replace")
    if p.returncode != 0 or "\n" not in stdout:
        return 0, ""
    body, _, code = stdout.rpartition("\n")
    try:
        return int(code), body
    except ValueError:
        return 0, ""
