import { cn } from "@/lib/utils"
import { confName } from "@/lib/types"

export interface Filters {
  confs: Set<string>
  regions: Set<string>
  years: Set<string> // "2024" … or "old" for the long tail
}

function Group({
  title,
  allActive,
  allCount,
  onAll,
  children,
}: {
  title: string
  allActive: boolean
  allCount: number
  onAll: () => void
  children: React.ReactNode
}) {
  return (
    <div className="mb-6">
      <p className="mb-2 text-[13px] text-muted-foreground">{title}</p>
      <div className="flex flex-col gap-0.5">
        <Row active={allActive} label="All" count={allCount} onClick={onAll} />
        {children}
      </div>
    </div>
  )
}

function Row({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean
  label: string
  count: number
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[13.5px] transition-colors",
        active
          ? "bg-foreground text-background"
          : "text-foreground/85 hover:bg-accent"
      )}
    >
      <span>{label}</span>
      <span className={cn("tabular-nums text-xs", active ? "text-background/70" : "text-muted-foreground")}>
        {count.toLocaleString()}
      </span>
    </button>
  )
}

export function FilterSidebar({
  filters,
  setFilters,
  conferences,
  confCounts,
  regionCounts,
  years,
  yearCounts,
  oldestIndividualYear,
  resultCount,
  total,
  className,
}: {
  filters: Filters
  setFilters: (f: Filters) => void
  conferences: string[]
  confCounts: Record<string, number>
  regionCounts: Record<string, number>
  years: number[]
  yearCounts: Record<string, number>
  oldestIndividualYear: number
  resultCount: number
  total: number
  className?: string
}) {
  const toggle = (set: Set<string>, v: string) => {
    const next = new Set(set)
    if (next.has(v)) next.delete(v)
    else next.add(v)
    return next
  }
  const hasActive = filters.confs.size > 0 || filters.regions.size > 0 || filters.years.size > 0

  return (
    <aside className={className} aria-label="Filters">
      <p className="mb-4 text-[13px] text-muted-foreground tabular-nums">
        {resultCount === total ? `${total.toLocaleString()} talks` : `${resultCount.toLocaleString()} of ${total.toLocaleString()}`}
      </p>

      {conferences.length > 1 && (
        <Group
          title="Conference"
          allActive={filters.confs.size === 0}
          allCount={total}
          onAll={() => setFilters({ ...filters, confs: new Set() })}
        >
          {conferences.map((c) => (
            <Row
              key={c}
              active={filters.confs.has(c)}
              label={confName(c)}
              count={confCounts[c] ?? 0}
              onClick={() => setFilters({ ...filters, confs: toggle(filters.confs, c) })}
            />
          ))}
        </Group>
      )}

      <Group
        title="Region"
        allActive={filters.regions.size === 0}
        allCount={total}
        onAll={() => setFilters({ ...filters, regions: new Set() })}
      >
        {(["us", "eu", "asia"] as const).map((r) => (
          <Row
            key={r}
            active={filters.regions.has(r)}
            label={r === "us" ? "US" : r === "eu" ? "EU" : "Asia"}
            count={regionCounts[r] ?? 0}
            onClick={() => setFilters({ ...filters, regions: toggle(filters.regions, r) })}
          />
        ))}
      </Group>

      <Group
        title="Year"
        allActive={filters.years.size === 0}
        allCount={total}
        onAll={() => setFilters({ ...filters, years: new Set() })}
      >
        <div className="max-h-64 overflow-y-auto pr-1 flex flex-col gap-0.5">
          {years
            .filter((y) => y >= oldestIndividualYear)
            .map((y) => (
              <Row
                key={y}
                active={filters.years.has(String(y))}
                label={String(y)}
                count={yearCounts[String(y)] ?? 0}
                onClick={() =>
                  setFilters({ ...filters, years: toggle(filters.years, String(y)) })
                }
              />
            ))}
          {(yearCounts["old"] ?? 0) > 0 && (
            <Row
              active={filters.years.has("old")}
              label={`before ${oldestIndividualYear}`}
              count={yearCounts["old"] ?? 0}
              onClick={() => setFilters({ ...filters, years: toggle(filters.years, "old") })}
            />
          )}
        </div>
      </Group>

      {hasActive && (
        <button
          type="button"
          onClick={() => setFilters({ confs: new Set(), regions: new Set(), years: new Set() })}
          className="text-[13px] text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          reset filters
        </button>
      )}
    </aside>
  )
}
