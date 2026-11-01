export interface Speaker {
  name: string
  company: string | null
  role: string | null
}

export interface Session {
  id: string
  conference?: string
  event: { region: "us" | "eu" | "asia"; year: number; label: string }
  title: string
  speakers: Speaker[]
  abstract: string
  track: string | null
  files: { slides: string | null; whitepaper: string | null; tool: string | null }
  video_url: string | null
  source_url: string | null
}

export interface Dataset {
  version: string
  conferences?: string[]
  sessions: Session[]
}

export const CONF_NAMES: Record<string, string> = {
  blackhat: "Black Hat",
  defcon: "DEF CON",
  ccc: "CCC",
  usenix: "USENIX",
  offensivecon: "OffensiveCon",
  hitcon: "HITCON",
  kcon: "KCon",
  redteamvillage: "Red Team Village",
  x33fcon: "x33fcon",
}

export function confName(id?: string): string {
  if (!id) return "Black Hat"
  return CONF_NAMES[id] ?? id
}

/** Compact hyphen-safe names for row badges: BlackHat-US-2024, DEFCON-2024 */
export function confShort(id?: string): string {
  if (!id) return "BlackHat"
  return (CONF_SHORT[id] ?? CONF_NAMES[id] ?? id).replace(/\s+/g, "")
}

const CONF_SHORT: Record<string, string> = {
  blackhat: "BlackHat",
  defcon: "DEFCON",
  ccc: "CCC",
  usenix: "USENIX",
  offensivecon: "OffensiveCon",
  hitcon: "HITCON",
  kcon: "KCon",
  redteamvillage: "RTV",
  x33fcon: "x33fcon",
}

export interface DatasetMeta {
  total: number
  withMaterials: number
  years: number[]
  oldestYear: number
  conferences: string[]
}

export function metaOf(ds: Dataset): DatasetMeta {
  // year=0 means unknown (render-batch adapters) — never surface it as a chip
  const years = [...new Set(ds.sessions.map((s) => s.event.year).filter((y) => y > 0))].sort(
    (a, b) => b - a
  )
  return {
    total: ds.sessions.length,
    withMaterials: ds.sessions.filter((s) => s.files.slides || s.files.whitepaper).length,
    years,
    oldestYear: years[years.length - 1] ?? 0,
    conferences: [...new Set(ds.sessions.map((s) => s.conference ?? "blackhat"))],
  }
}
