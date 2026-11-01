import { useState } from "react"
import { confShort, type Session } from "@/lib/types"

function Highlight({ text, terms }: { text: string; terms: Set<string> }) {
  if (!text) return null
  if (terms.size === 0) return <>{text}</>
  const pattern = Array.from(terms, (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")
  const parts = text.split(new RegExp(`(${pattern})`, "gi"))
  return (
    <>
      {parts.map((p, i) =>
        terms.has(p.toLowerCase()) ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>
      )}
    </>
  )
}

function FileLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-4 decoration-line hover:decoration-foreground transition-colors"
    >
      {children}
    </a>
  )
}

export function ResultRow({ s, terms }: { s: Session; terms: Set<string> }) {
  const [expanded, setExpanded] = useState(false)
  const speakerLine = s.speakers
    .map((p) => (p.company ? `${p.name} (${p.company})` : p.name))
    .join("; ")
  const long = s.abstract.length > 320
  // classification badge: {Conference}-{Region}-{Year} (region only where it
  // is a real distinction, i.e. Black Hat editions)
  const regionTag = s.event.label.match(/^(US|EU|Asia)-/)?.[1]
  const badge = [confShort(s.conference), regionTag, s.event.year > 0 ? s.event.year : null]
    .filter(Boolean)
    .join("-")

  return (
    <article className="py-5 border-b border-line">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="text-[15px] font-semibold leading-snug">
          {s.source_url ? (
            <a
              href={s.source_url}
              target="_blank"
              rel="noreferrer"
              className="hover:underline underline-offset-4 decoration-transparent hover:decoration-foreground transition-colors"
            >
              <Highlight text={s.title} terms={terms} />
            </a>
          ) : (
            <Highlight text={s.title} terms={terms} />
          )}
        </h3>
        <span className="shrink-0 rounded-md border border-line px-2 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">
          {badge}
        </span>
      </div>
      {speakerLine && (
        <p className="mt-1 text-[13px] text-muted-foreground">
          <Highlight text={speakerLine} terms={terms} />
        </p>
      )}
      {s.abstract && (
        <p
          className={
            "mt-2 text-[13.5px] leading-relaxed text-abstract " +
            (expanded || !long ? "" : "line-clamp-3")
          }
        >
          <Highlight text={s.abstract} terms={terms} />
        </p>
      )}
      <p className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[13px]">
        {s.files.slides && <FileLink href={s.files.slides}>Slides</FileLink>}
        {s.files.whitepaper && <FileLink href={s.files.whitepaper}>Whitepaper</FileLink>}
        {s.files.tool && <FileLink href={s.files.tool}>Tool</FileLink>}
        {s.video_url && <FileLink href={s.video_url}>Video</FileLink>}
        {long && (
          <button
            type="button"
            className="text-muted-foreground underline underline-offset-4 hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "less" : "more"}
          </button>
        )}
      </p>
    </article>
  )
}
