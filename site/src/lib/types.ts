export interface Speaker {
  name: string
  company: string | null
  role: string | null
}

/** slimmed payloads omit empty fields — every field beyond id/event/title is optional */
export interface Session {
  id: string
  conference?: string
  event: { region: "us" | "eu" | "asia"; year: number; label: string }
  title: string
  speakers?: Speaker[]
  abstract?: string
  track?: string | null
  files?: { slides?: string | null; whitepaper?: string | null; tool?: string | null }
  video_url?: string | null
  source_url?: string | null
}

export interface ConferenceInfo {
  id: string
  name: string
  url: string | null
  description?: string | null
}

export interface Dataset {
  version: string
  conferences?: (string | ConferenceInfo)[]
  sessions: Session[]
}

/** tiny first-paint payload: structure + counts without the sessions bulk */
export interface Manifest {
  version: string
  total: number
  conferences: ConferenceInfo[]
  editions: {
    key: string
    conference: string
    region: string
    year: number
    label: string
    count: number
  }[]
}

/** manifest comes from the crawler adapters via the dataset; the builtin
 * map below is only a fallback for older datasets / unknown ids */
export function conferenceList(ds: { conferences?: (string | ConferenceInfo)[] }): ConferenceInfo[] {
  return (ds.conferences ?? ["blackhat"]).map((c) =>
    typeof c === "string"
      ? { id: c, name: CONF_NAMES[c] ?? c, url: null, description: null }
      : { description: null, ...c }
  )
}

export function editionKey(s: { conference?: string; event: { region: string; year: number } }): string {
  return `${s.conference ?? "blackhat"}|${s.event.region}|${s.event.year}`
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
  pretalx: "Pretalx cons",
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
  pretalx: "Pretalx cons",
}

export interface DatasetMeta {
  total: number
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
    years,
    oldestYear: years[years.length - 1] ?? 0,
    conferences: [...new Set(ds.sessions.map((s) => s.conference ?? "blackhat"))],
  }
}
