# hatstack

**Every security conference, one search box.**

A searchable index of security-conference archives: talk titles, speakers,
abstracts, and official slide / whitepaper / video links — Black Hat, DEF CON,
CCC, USENIX Security and more, from 1984 to today, in one page.

**Live site:** <https://xiaolichan.github.io/hatstack/>

## What's indexed

| conference | span | channel | status |
|---|---|---|---|
| Black Hat (US/EU/Asia) | 1997– | Wayback Machine (≤2025) + live capture (2026–) | ✅ |
| DEF CON (+ villages) | 1993– | `media.defcon.org` static autoindex | ✅ |
| CCC family (Congress/Camp/GPN/EH/MRMCD/DS/FiffKon/DIVOC) | 1984– | `api.media.ccc.de` JSON API | ✅ |
| USENIX Security | 2015– | static listing pages | ✅ |
| OffensiveCon | 2020– | static speaker pages | ✅ |
| Red Team Village | — | SPA render (Playwright) | 🔄 parser tuning |
| x33fcon | 2017– | SPA render (Playwright) | 🔄 parser tuning |
| Troopers / Nullcon / hack.lu / HITB / small cons / BSides family | — | — | 📋 roadmap |

Monthly GitHub Actions runs refresh everything and commit the dataset;
partial runs merge into the committed dataset (never wipe).

## How it works

```
conference sites ──(one adapter per conf, crawler/confs/)──▶ dataset/dataset.json
dataset/dataset.json ──(Vite + React + shadcn/ui + MiniSearch)──▶ GitHub Pages
```

Each adapter picks the cheapest channel that works:

- **official JSON APIs** — CCC (`api.media.ccc.de`)
- **static autoindexes via curl** — DEF CON (`media.defcon.org`; its CDN
  rejects urllib3's TLS fingerprint, so listings go through subprocess curl)
- **static listing pages** — USENIX Security, OffensiveCon
- **Wayback Machine** — Black Hat ≤2025 (sidesteps blackhat.com's Cloudflare
  entirely: newest 200 capture via `id_` original-byte fetches, 429 backoff)
- **headless Chromium render** — JS-shell sites (x33fcon, Red Team Village);
  Black Hat ≥2026 uses the fresh-browser-per-event + XHR-capture engine that
  solved its Cloudflare challenge
- **one fresh browser per event** where a challenge must be passed

The site is a single page: instant search (MiniSearch, field-weighted
title > speakers > abstract, separator-insensitive — `zero-day`, `zero day`
and `zeroday` all match, adjacent compounds only), conference × region ×
year filters, shareable `?q=` links, dark by default. Files are hotlinked to
their official hosts — nothing is mirrored.

## Add a conference

```
crawler/confs/<id>.py   # ID, NAME, collect(ctx) -> {event_key: capture}
```

Register the id in `crawler/confs/__init__.py`, parse into the shared session
schema (see `defcon.py` for the simplest full example), add tests, done — the
workflow, dataset merge and site filters pick it up automatically.

## Usage

- **Search:** use the site. `/` focuses the box.
- **Re-crawl:** Actions → *Crawl* → *Run workflow* (limit / events / confs /
  refresh / commit), or locally:
  ```bash
  pip install -r crawler/requirements.txt && playwright install chromium --with-deps
  python -m crawler crawl                    # all conferences
  python -m crawler crawl --confs defcon ccc # just some
  pytest crawler/tests                       # 21 tests
  ```
- **Bulk PDFs** (this repo's original purpose): Actions → *Download PDFs* →
  pick an event (e.g. `US-24`) → grab the tarball artifact.

## Repository layout

| path | what |
|---|---|
| `crawler/confs/` | per-conference adapters |
| `crawler/{events,wayback,capture,render,net,parse,dataset,cli}.py` | shared engine |
| `dataset/` | `dataset.json` + completeness report (committed, auto-refreshed) |
| `crawler/cache/` | raw captures per conf (committed → incremental runs) |
| `site/` | Vite + React + TS + shadcn/ui front-end |
| `.github/workflows/` | Crawl (monthly), Site (Pages), Download PDFs, Egress Probe |

## Credits & license

- Site and crawler code: **CC0** (see `LICENSE`), inspired by
  [ippsec.rocks](https://ippsec.rocks) (CC0).
- Talk metadata and materials belong to their authors and the conferences;
  this index only links to official files.
