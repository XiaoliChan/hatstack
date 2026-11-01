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
  compound: string
}> {
  const mini = new MiniSearch({
    fields: ["title", "speakers", "abstract", "compound"],
    storeFields: ["id"],
  })
  mini.addAll(
    sessions.map((s) => {
      const words =
        `${s.title} ${s.abstract}`.toLowerCase().split(/[^a-z0-9+#.]+/).filter(Boolean)
      // adjacent-token concatenations: "zero day" -> "zeroday",
      // so separator-less queries match hyphenated/spaced text and vice versa
      const compound = new Set<string>()
      for (let i = 0; i < words.length - 1; i++) {
        const joined = words[i] + words[i + 1]
        if (joined.length <= 24) compound.add(joined)
        const tri = words[i + 2] ? words[i] + words[i + 1] + words[i + 2] : ""
        if (tri.length > 0 && tri.length <= 24) compound.add(tri)
      }
      return {
        id: s.id,
        title: s.title,
        speakers: s.speakers.map((p) => p.name).join(" "),
        abstract: s.abstract,
        compound: [...compound].join(" "),
      }
    })
  )
  return mini
}

export function runSearch(
  index: MiniSearch<{ id: string; title: string; speakers: string; abstract: string; compound: string }>,
  query: string,
  allowed: Set<string>
): SearchHit[] {
  const opts = {
    // compound (adjacent concatenations, e.g. "zero day"->"zeroday") ranks with
    // titles so adjacent matches clearly outrank scattered all-terms matches
    boost: { title: 3, compound: 3, speakers: 2, abstract: 1 } as Record<string, number>,
    prefix: true,
    fuzzy: 0.2,
  }
  const merged = new Map<string, number>()
  for (const r of index.search(query, opts)) {
    merged.set(r.id, (merged.get(r.id) ?? 0) + r.score)
  }
  // separator-less variant: "zero day" also matches text written "zeroday"
  const tokens = query.toLowerCase().split(/[^a-z0-9+#.]+/).filter((t) => t.length >= 2)
  if (tokens.length >= 2) {
    for (const r of index.search(tokens.join(""), opts)) {
      merged.set(r.id, (merged.get(r.id) ?? 0) + r.score)
    }
  }
  return [...merged]
    .filter(([id]) => allowed.has(id))
    .map(([id, score]) => ({ id, score }))
    .sort((a, b) => b.score - a.score)
}

export function queryTerms(query: string): string[] {
  const tokens = query
    .toLowerCase()
    .split(/[^a-z0-9+#.-]+/)
    .filter((t) => t.length >= 2)
    .slice(0, 8)
  if (tokens.length >= 2) {
    const joined = tokens.join("")
    if (joined.length <= 26 && !tokens.includes(joined)) tokens.push(joined)
  }
  return tokens
}
