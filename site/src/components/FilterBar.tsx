import { confName } from "@/lib/types"
import { cn } from "@/lib/utils"

function Chip({
  active,
  children,
  onClick,
  title,
}: {
  active: boolean
  children: React.ReactNode
  onClick: () => void
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={title}
      className={cn(
        "rounded-full border px-3 py-1 text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-ring",
        active
          ? "bg-foreground text-background border-foreground"
          : "border-line text-muted-foreground hover:text-foreground hover:border-foreground/40"
      )}
    >
      {children}
    </button>
  )
}

export interface Filters {
  confs: Set<string>
  regions: Set<string>
  years: Set<string> // "2024" … or "old" for the long tail
}

export function FilterBar({
  filters,
  setFilters,
  years,
  oldestIndividualYear,
  conferences,
  resultCount,
  total,
}: {
  filters: Filters
  setFilters: (f: Filters) => void
  years: number[]
  oldestIndividualYear: number
  conferences: string[]
  resultCount: number
  total: number
}) {
  const toggle = (set: Set<string>, v: string) => {
    const next = new Set(set)
    if (next.has(v)) next.delete(v)
    else next.add(v)
    return next
  }
  const hasActive = filters.confs.size > 0 || filters.regions.size > 0 || filters.years.size > 0

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
      {conferences.length > 1 && (
        <>
          <div className="flex gap-1.5" role="group" aria-label="Filter by conference">
            {conferences.map((c) => (
              <Chip
                key={c}
                active={filters.confs.has(c)}
                onClick={() => setFilters({ ...filters, confs: toggle(filters.confs, c) })}
              >
                {confName(c)}
              </Chip>
            ))}
          </div>
          <span className="text-line select-none" aria-hidden>
            |
          </span>
        </>
      )}
      <div className="flex gap-1.5" role="group" aria-label="Filter by region">
        {(["us", "eu", "asia"] as const).map((r) => (
          <Chip
            key={r}
            active={filters.regions.has(r)}
            onClick={() => setFilters({ ...filters, regions: toggle(filters.regions, r) })}
          >
            {r === "us" ? "US" : r === "eu" ? "EU" : "Asia"}
          </Chip>
        ))}
      </div>
      <span className="text-line select-none" aria-hidden>
        |
      </span>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by year">
        {years
          .filter((y) => y >= oldestIndividualYear)
          .map((y) => (
            <Chip
              key={y}
              active={filters.years.has(String(y))}
              onClick={() =>
                setFilters({ ...filters, years: toggle(filters.years, String(y)) })
              }
            >
              {y}
            </Chip>
          ))}
        {years.some((y) => y < oldestIndividualYear) && (
          <Chip
            active={filters.years.has("old")}
            onClick={() => setFilters({ ...filters, years: toggle(filters.years, "old") })}
            title={`Before ${oldestIndividualYear}`}
          >
            &lt;{oldestIndividualYear}
          </Chip>
        )}
      </div>
      <span className="ml-auto text-[13px] text-muted-foreground tabular-nums">
        {resultCount === total ? `${total} talks` : `${resultCount} of ${total}`}
        {hasActive && (
          <button
            type="button"
            className="ml-3 underline underline-offset-4 hover:text-foreground"
            onClick={() => setFilters({ confs: new Set(), regions: new Set(), years: new Set() })}
          >
            reset
          </button>
        )}
      </span>
    </div>
  )
}
