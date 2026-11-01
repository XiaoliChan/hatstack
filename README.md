# BlackHat-Scrapy

A searchable index of Black Hat briefings — every talk from **US, EU and Asia,
1997 to today**: title, speakers, abstract, and official slide / whitepaper /
tool links, searchable in the browser.

**Live site:** <https://xiaolichan.github.io/BlackHat-Scrapy/>

## How it works

```
blackhat.com ──(Playwright crawler, one fresh browser per event)──▶ dataset/dataset.json
dataset/dataset.json ──(Vite + React + shadcn/ui + MiniSearch)──▶ GitHub Pages
```

- **Crawler** (`crawler/`): opens each event's schedule page in its own fresh
  Chromium process, waits out the Cloudflare challenge, and captures the page's
  own `sessions.json` XHR (2018+ events). Older events (≤2017) are static HTML
  pages parsed directly. Runs monthly via GitHub Actions and commits the
  dataset. PDFs are hotlinked from the official CDN — nothing is mirrored.
- **Site** (`site/`): single-page instant search (MiniSearch, field-weighted
  title > speakers > abstract), region × year filters, shareable `?q=` links,
  dark by default.

## Usage

- **Search:** just use the site. Press `/` to focus the box.
- **Re-crawl now:** Actions → *Crawl* → *Run workflow* (options: limit, events,
  refresh, commit).
- **Bulk-download PDFs for offline reading** (the repo's original purpose):
  Actions → *Download PDFs* → pick an event (e.g. `US-24`) → grab the artifact.
- **Local crawler:**
  ```bash
  pip install -r crawler/requirements.txt && playwright install chromium --with-deps
  python -m crawler crawl --events us-24 eu-23     # specific events
  python -m crawler download --event US-24          # PDFs into ./save/US-24
  ```
  Note: blackhat.com is behind Cloudflare; the crawler works from GitHub
  Actions runners and most residential IPs.

## Repository layout

| path | what |
|---|---|
| `crawler/` | Python crawler + parsers + tests (`pytest crawler/tests`) |
| `dataset/` | crawled dataset (`dataset.json`) + completeness report |
| `site/` | Vite + React + TS + shadcn/ui front-end |
| `.github/workflows/` | Crawl (monthly), Site (Pages), Download PDFs (manual), Egress Probe (diagnostics) |

## Credits & license

- Site and crawler code: **CC0** (see `LICENSE`), inspired by
  [ippsec.rocks](https://ippsec.rocks) (CC0).
- Talk titles, abstracts and materials belong to their authors and Black Hat;
  this index only links to the official blackhat.com files.
