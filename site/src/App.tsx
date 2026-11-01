import { useEffect, useMemo, useState } from "react"
import { FilterSidebar, type EditionGroup, type Filters } from "@/components/FilterSidebar"
import { ResultRow } from "@/components/ResultRow"
import { SearchBox } from "@/components/SearchBox"
import { ThemeToggle } from "@/components/ThemeToggle"
import { buildIndex, queryTerms, runSearch } from "@/lib/search"
import { conferenceList, editionKey, metaOf, type Dataset } from "@/lib/types"

const PAGE = 50

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [query, setQuery] = useState(
    () => new URLSearchParams(window.location.search).get("q") ?? ""
  )
  const [debounced, setDebounced] = useState(query)
  const [filters, setFilters] = useState<Filters>({ edition: null })
  const [page, setPage] = useState(1)
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    // cache-bust: Pages caches dataset.json ~10min and stale data after a
    // crawl deploy is the single most confusing failure for visitors
    fetch(`${import.meta.env.BASE_URL}dataset.json?t=${Date.now()}`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.json()
      })
      .then(setDataset)
      .catch(() => setLoadError(true))
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 300)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (debounced) params.set("q", debounced)
    else params.delete("q")
    const qs = params.toString()
    window.history.replaceState(null, "", qs ? `${window.location.pathname}?${qs}` : window.location.pathname)
    setPage(1)
  }, [debounced])

  useEffect(() => setPage(1), [filters])

  const index = useMemo(() => (dataset ? buildIndex(dataset.sessions) : null), [dataset])
  const meta = useMemo(() => (dataset ? metaOf(dataset) : null), [dataset])

  const groups = useMemo<EditionGroup[]>(() => {
    if (!dataset) return []
    const confs = conferenceList(dataset)
    const byConf = new Map<string, Map<string, { label: string; count: number }>>()
    const regionsPerConf = new Map<string, Set<string>>()
    const totals = new Map<string, number>()
    for (const s of dataset.sessions) {
      const conf = s.conference ?? "blackhat"
      totals.set(conf, (totals.get(conf) ?? 0) + 1)
      const regions = regionsPerConf.get(conf) ?? new Set()
      regions.add(s.event.region)
      regionsPerConf.set(conf, regions)
      const key = editionKey(s)
      const m = byConf.get(conf) ?? new Map()
      const cur = m.get(key)
      if (cur) cur.count += 1
      else m.set(key, { label: "", count: 1 })
      byConf.set(conf, m)
    }
    return confs
      .filter((c) => (totals.get(c.id) ?? 0) > 0)
      .map((c) => {
        const multiRegion = (regionsPerConf.get(c.id)?.size ?? 0) > 1
        const editions = [...(byConf.get(c.id)?.entries() ?? [])]
          .map(([key, v]) => {
            const [, region, yearStr] = key.split("|")
            const year = Number(yearStr)
            const regionTag = multiRegion ? region.toUpperCase() : null
            const label =
              year > 0 ? [regionTag, year].filter(Boolean).join("-") : [regionTag, "unknown"].filter(Boolean).join("-")
            return { key, label, count: v.count }
          })
          .sort((a, b) => {
            const ya = Number(a.key.split("|")[2])
            const yb = Number(b.key.split("|")[2])
            if (ya !== yb) return (yb > 0 ? yb : -1) - (ya > 0 ? ya : -1) // newest first, unknown last
            return a.label.localeCompare(b.label)
          })
        return { conf: c, editions, count: totals.get(c.id) ?? 0 }
      })
  }, [dataset])

  const results = useMemo(() => {
    if (!dataset || !index) return []
    const edition = filters.edition
    const allowed = new Set(
      dataset.sessions
        .filter((s) => {
          if (!edition) return true
          if (!edition.includes("|")) return (s.conference ?? "blackhat") === edition
          return editionKey(s) === edition
        })
        .map((s) => s.id)
    )
    if (!debounced) {
      return dataset.sessions.filter((s) => allowed.has(s.id))
    }
    const hits = runSearch(index, debounced, allowed)
    const byId = new Map(dataset.sessions.map((s) => [s.id, s]))
    return hits.map((h) => byId.get(h.id)).filter((s): s is NonNullable<typeof s> => !!s)
  }, [dataset, index, debounced, filters])

  const terms = useMemo(() => new Set(queryTerms(debounced)), [debounced])

  const totalPages = Math.max(1, Math.ceil(results.length / PAGE))
  const pageRows = results.slice((page - 1) * PAGE, page * PAGE)
  const pageNumbers = useMemo(() => {
    const nums: (number | "…")[] = []
    for (let i = 1; i <= totalPages; i++) {
      if (i <= 2 || i > totalPages - 2 || Math.abs(i - page) <= 1) nums.push(i)
      else if (nums[nums.length - 1] !== "…") nums.push("…")
    }
    return nums
  }, [page, totalPages])

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-5 md:px-8">
        <header className="flex items-center justify-between gap-4 pt-8 pb-2">
          <h1 className="text-[15px] font-bold tracking-tight">hatstack</h1>
          <div className="flex items-center gap-2">
            <a
              href="https://xiaolichan.github.io/"
              title="XiaoliChan's homepage"
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-line text-[13px] text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                <path d="M9 22V12h6v10" />
              </svg>
              home
            </a>
            <ThemeToggle />
          </div>
        </header>
        <p className="text-[13px] text-muted-foreground pb-6">
          {meta ? (
            <>
              every security conference, one search box · {meta.total.toLocaleString()} talks ·{" "}
              {meta.withMaterials.toLocaleString()} with materials · {meta.oldestYear}–{meta.years[0]}
            </>
          ) : loadError ? (
            "Couldn't load dataset.json"
          ) : (
            "Loading index…"
          )}
        </p>

        <SearchBox value={query} onChange={setQuery} />

        <button
          type="button"
          onClick={() => setShowFilters((v) => !v)}
          className="mt-4 lg:hidden text-[13px] text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          {showFilters ? "hide filters" : "filters"}
        </button>

        <div className="mt-4 lg:grid lg:grid-cols-[240px_1fr] lg:gap-10">
          {meta && (
            <FilterSidebar
              filters={filters}
              setFilters={setFilters}
              groups={groups}
              resultCount={results.length}
              total={meta.total}
              className={`${showFilters ? "block mb-6" : "hidden"} lg:block lg:sticky lg:top-6 lg:self-start`}
            />
          )}

          <main aria-live="polite">
            {loadError && (
              <p className="py-10 text-sm text-muted-foreground">
                Couldn't load the dataset. Refresh the page, or check the{" "}
                <a
                  className="underline underline-offset-4"
                  href="https://github.com/XiaoliChan/hatstack"
                  target="_blank"
                  rel="noreferrer"
                >
                  repository
                </a>
                .
              </p>
            )}
            {dataset && results.length === 0 && (
              <div className="py-10 text-sm text-muted-foreground">
                <p>No talks match {debounced ? `“${debounced}”` : "these filters"}.</p>
                <button
                  type="button"
                  className="mt-2 underline underline-offset-4 hover:text-foreground"
                  onClick={() => {
                    setQuery("")
                    setFilters({ edition: null })
                  }}
                >
                  reset search and filters
                </button>
              </div>
            )}
            {pageRows.map((s) => (
              <ResultRow key={s.id} s={s} terms={terms} />
            ))}
            {totalPages > 1 && (
              <nav className="flex items-center justify-center gap-2 py-8" aria-label="Pagination">
                <button
                  type="button"
                  disabled={page === 1}
                  onClick={() => { setPage((p) => p - 1); window.scrollTo({ top: 0 }) }}
                  className="h-8 px-3 rounded-md border border-line text-[13px] text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors disabled:opacity-30 disabled:pointer-events-none"
                >
                  prev
                </button>
                {pageNumbers.map((n, i) =>
                  n === "…" ? (
                    <span key={`e${i}`} className="text-muted-foreground/60 text-[13px] px-1">…</span>
                  ) : (
                    <button
                      key={n}
                      type="button"
                      onClick={() => { setPage(n); window.scrollTo({ top: 0 }) }}
                      aria-current={n === page ? "page" : undefined}
                      className={
                        "h-8 min-w-8 px-2 rounded-md text-[13px] tabular-nums transition-colors " +
                        (n === page
                          ? "bg-foreground text-background"
                          : "border border-line text-muted-foreground hover:text-foreground hover:border-foreground/40")
                      }
                    >
                      {n}
                    </button>
                  )
                )}
                <button
                  type="button"
                  disabled={page === totalPages}
                  onClick={() => { setPage((p) => p + 1); window.scrollTo({ top: 0 }) }}
                  className="h-8 px-3 rounded-md border border-line text-[13px] text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors disabled:opacity-30 disabled:pointer-events-none"
                >
                  next
                </button>
              </nav>
            )}
          </main>
        </div>

        <footer className="mt-16 pb-10 text-xs leading-relaxed text-muted-foreground/70">
          <p>
            Talks and materials belong to their authors and the conferences. This index links to
            official files; the code is CC0.
          </p>
          <p className="mt-1">
            <a
              className="underline underline-offset-4 hover:text-muted-foreground"
              href="https://github.com/XiaoliChan/hatstack"
              target="_blank"
              rel="noreferrer"
            >
              Source &amp; crawler
            </a>
            {dataset && ` · dataset ${dataset.version}`}
          </p>
        </footer>
      </div>
    </div>
  )
}
