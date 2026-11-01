export interface Speaker {
  name: string
  company: string | null
  role: string | null
}

export interface Session {
  id: string
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
  sessions: Session[]
}

export interface DatasetMeta {
  total: number
  withMaterials: number
  years: number[]
  oldestYear: number
}

export function metaOf(ds: Dataset): DatasetMeta {
  const years = [...new Set(ds.sessions.map((s) => s.event.year))].sort((a, b) => b - a)
  return {
    total: ds.sessions.length,
    withMaterials: ds.sessions.filter((s) => s.files.slides || s.files.whitepaper).length,
    years,
    oldestYear: years[years.length - 1] ?? 0,
  }
}
