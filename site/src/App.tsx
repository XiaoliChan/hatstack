import { useEffect, useMemo, useRef, useState } from "react"
import { FilterBar, type Filters } from "@/components/FilterBar"
import { ResultRow } from "@/components/ResultRow"
import { SearchBox } from "@/components/SearchBox"
import { ThemeToggle } from "@/components/ThemeToggle"
import { buildIndex, queryTerms, runSearch } from "@/lib/search"
import { metaOf, type Dataset } from "@/lib/types"

const PAGE = 50

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [query, setQuery] = useState(
    () => new URLSearchParams(window.location.search).get("q") ?? ""
  )
  const [debounced, setDebounced] = useState(query)
  const [filters, setFilters] = useState<Filters>({ confs: new Set(), regions: new Set(), years: new Set() })
  const [visible, setVisible] = useState(PAGE)
  const sentinel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}dataset.json`)
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
    setVisible(PAGE)
  }, [debounced])

  useEffect(() => setVisible(PAGE), [filters])

  const index = useMemo(() => (dataset ? buildIndex(dataset.sessions) : null), [dataset])
  const meta = useMemo(() => (dataset ? metaOf(dataset) : null), [dataset])

  const oldestIndividual = useMemo(() => {
    if (!meta || !meta.years.length) return 2015
    const distinct = meta.years.length
    return distinct > 14 ? meta.years[13] : Math.min(meta.years[0] - 1, meta.years[meta.years.length - 1])
  }, [meta])

  const results = useMemo(() => {
    if (!dataset || !index) return []
    const allowed = new Set(
      dataset.sessions
        .filter((s) => {
          if (filters.confs.size && !filters.confs.has(s.conference ?? "blackhat")) return false
          if (filters.regions.size && !filters.regions.has(s.event.region)) return false
          if (filters.years.size) {
            const bucket =
              s.event.year >= oldestIndividual ? String(s.event.year) : "old"
            if (!filters.years.has(bucket)) return false
          }
          return true
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

  const filtersActive = filters.confs.size > 0 || filters.regions.size > 0 || filters.years.size > 0
  const showResults = debounced !== "" || filtersActive

  const SUGGESTIONS = ["kerberos", "active directory", "windows kernel", "dns", "zero-day", "supply chain"]

  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) setVisible((v) => v + PAGE)
      },
      { rootMargin: "600px" }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [sentinel])

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-5 md:px-8">
        <header className="flex items-center justify-between gap-4 pt-8 pb-2">
          <h1 className="text-[15px] font-bold tracking-tight">Black Hat Briefings</h1>
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
              {meta.total.toLocaleString()} talks · {meta.withMaterials.toLocaleString()} with
              materials · {meta.oldestYear}–{meta.years[0]}
            </>
          ) : loadError ? (
            "Couldn't load dataset.json"
          ) : (
            "Loading index…"
          )}
        </p>

        <SearchBox value={query} onChange={setQuery} />

        <div className="mt-5">
          {meta && (
            <FilterBar
              filters={filters}
              setFilters={setFilters}
              years={meta.years}
              oldestIndividualYear={oldestIndividual}
              conferences={meta.conferences}
              resultCount={results.length}
              total={meta.total}
            />
          )}
        </div>

        <main className="mt-4" aria-live="polite">
          {meta && !showResults && (
            <div className="py-14 text-center">
              <p className="text-sm text-muted-foreground">
                Type to search {meta.total.toLocaleString()} talks — or pick a starting point:
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setQuery(s)}
                    className="rounded-full border border-line px-3.5 py-1.5 text-[13px] text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
              <p className="mt-6 text-xs text-muted-foreground/70">
                Or filter by region and year above to browse a single event.
              </p>
            </div>
          )}
          {loadError && (
            <p className="py-10 text-sm text-muted-foreground">
              Couldn't load the dataset. Refresh the page, or check the{" "}
              <a
                className="underline underline-offset-4"
                href="https://github.com/XiaoliChan/BlackHat-Scrapy"
                target="_blank"
                rel="noreferrer"
              >
                repository
              </a>
              .
            </p>
          )}
          {dataset && showResults && results.length === 0 && (
            <div className="py-10 text-sm text-muted-foreground">
              <p>No talks match {debounced ? `“${debounced}”` : "these filters"}.</p>
              <button
                type="button"
                className="mt-2 underline underline-offset-4 hover:text-foreground"
                onClick={() => {
                  setQuery("")
                  setFilters({ confs: new Set(), regions: new Set(), years: new Set() })
                }}
              >
                reset search and filters
              </button>
            </div>
          )}
          {showResults && results.slice(0, visible).map((s) => (
            <ResultRow key={s.id} s={s} terms={terms} />
          ))}
          <div ref={sentinel} />
          {showResults && results.length > visible && (
            <div className="py-8 text-center">
              <button
                type="button"
                className="border border-line rounded-full px-5 py-2 text-[13px] text-muted-foreground hover:text-foreground hover:border-foreground/40 transition-colors"
                onClick={() => setVisible((v) => v + PAGE)}
              >
                show more ({results.length - visible} left)
              </button>
            </div>
          )}
        </main>

        <footer className="mt-16 pb-10 text-xs leading-relaxed text-muted-foreground/70">
          <p>
            Talks and materials belong to their authors and Black Hat. This index links to the
            official blackhat.com files; the code is CC0.
          </p>
          <p className="mt-1">
            <a
              className="underline underline-offset-4 hover:text-muted-foreground"
              href="https://github.com/XiaoliChan/BlackHat-Scrapy"
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
