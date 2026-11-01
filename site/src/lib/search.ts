import MiniSearch from "minisearch"
import type { Session } from "./types"

export interface SearchHit {
  id: string
  score: number
}

export function buildIndex(sessions: Session[]): MiniSearch<{
  id: string
  title: string
  speakers: string
  abstract: string
}> {
  const mini = new MiniSearch({
    fields: ["title", "speakers", "abstract"],
    storeFields: ["id"],
  })
  mini.addAll(
    sessions.map((s) => ({
      id: s.id,
      title: s.title,
      speakers: s.speakers.map((p) => p.name).join(" "),
      abstract: s.abstract,
    }))
  )
  return mini
}

export function runSearch(
  index: MiniSearch<{ id: string; title: string; speakers: string; abstract: string }>,
  query: string,
  allowed: Set<string>
): SearchHit[] {
  const raw = index.search(query, {
    boost: { title: 3, speakers: 2, abstract: 1 },
    prefix: true,
    fuzzy: 0.2,
  })
  return raw.filter((r) => allowed.has(r.id)).map((r) => ({ id: r.id, score: r.score }))
}

export function queryTerms(query: string): string[] {
  return query
    .toLowerCase()
    .split(/[^a-z0-9+#.-]+/)
    .filter((t) => t.length >= 2)
    .slice(0, 8)
}
