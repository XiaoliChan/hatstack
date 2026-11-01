import { cn } from "@/lib/utils"
import { type ConferenceInfo } from "@/lib/types"

export interface Filters {
  /** single selection: "conf|region|year" for an edition, "conf" for a whole
   * conference, null for everything */
  edition: string | null
}

export interface EditionGroup {
  conf: ConferenceInfo
  editions: { key: string; label: string; count: number }[]
  count: number
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
        "flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-[13.5px] transition-colors w-full",
        active
          ? "bg-foreground text-background"
          : "text-foreground/85 hover:bg-accent"
      )}
    >
      <span className="truncate">{label}</span>
      <span className={cn("tabular-nums text-xs shrink-0", active ? "text-background/70" : "text-muted-foreground")}>
        {count.toLocaleString()}
      </span>
    </button>
  )
}

export function FilterSidebar({
  filters,
  setFilters,
  groups,
  resultCount,
  total,
  className,
}: {
  filters: Filters
  setFilters: (f: Filters) => void
  groups: EditionGroup[]
  resultCount: number
  total: number
  className?: string
}) {
  const clear = () => setFilters({ edition: null })
  const confActive = (g: EditionGroup) => filters.edition === g.conf.id
  const toggleConf = (g: EditionGroup) => {
    setFilters({ edition: confActive(g) ? null : g.conf.id })
  }

  return (
    <aside className={className} aria-label="Filters">
      <p className="mb-3 text-[13px] text-muted-foreground tabular-nums">
        {resultCount === total
          ? `${total.toLocaleString()} talks`
          : `${resultCount.toLocaleString()} of ${total.toLocaleString()}`}
      </p>

      <Row active={filters.edition === null} label="All" count={total} onClick={clear} />

      {groups.map((g) => (
        <div key={g.conf.id} className="mt-5">
          <div className="flex items-center justify-between gap-2 mb-1 group/row pr-1">
            <button
              type="button"
              onClick={() => toggleConf(g)}
              title={confActive(g) ? "Show all conferences" : `Show only ${g.conf.name}`}
              className={cn(
                "flex-1 min-w-0 text-left text-[14px] font-semibold truncate rounded-md px-2.5 py-1 transition-colors",
                confActive(g) ? "bg-accent" : "hover:text-foreground/70"
              )}
            >
              {g.conf.name}
            </button>
            <span className="tabular-nums text-xs text-muted-foreground shrink-0">
              {g.count.toLocaleString()}
            </span>
            {g.conf.url && (
              <a
                href={g.conf.url}
                target="_blank"
                rel="noreferrer"
                title={`${g.conf.name} official site`}
                className="shrink-0 p-1 text-muted-foreground/0 group-hover/row:text-muted-foreground hover:!text-foreground transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                  <path d="M15 3h6v6" />
                  <path d="M10 14 21 3" />
                </svg>
              </a>
            )}
          </div>
          {g.conf.description && (
            <p className="px-2.5 mb-1.5 text-[11.5px] leading-snug text-muted-foreground/80">
              {g.conf.description}
            </p>
          )}
          <div className="flex flex-col gap-0.5">
            {g.editions.map((e) => (
              <Row
                key={e.key}
                active={filters.edition === e.key}
                label={e.label}
                count={e.count}
                onClick={() => setFilters({ edition: filters.edition === e.key ? null : e.key })}
              />
            ))}
          </div>
        </div>
      ))}

      {filters.edition !== null && (
        <button
          type="button"
          onClick={clear}
          className="mt-5 text-[13px] text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          reset filters
        </button>
      )}
    </aside>
  )
}
