// Copy crawled payloads into the site's public dir before dev/build.
import { copyFileSync, existsSync, readdirSync, unlinkSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const src = resolve(here, "../dataset")
const dst = (f) => resolve(here, "public", f)

let copied = 0
for (const f of ["manifest.json"]) {
  if (existsSync(resolve(src, f))) {
    copyFileSync(resolve(src, f), dst(f))
    copied++
  }
}
const sessions = existsSync(src)
  ? readdirSync(src).filter((f) => /^sessions-v.+\.json$/.test(f)).sort().pop()
  : null
if (sessions) {
  copyFileSync(resolve(src, sessions), dst(sessions))
  copied++
  // prune superseded snapshots from public/
  for (const f of readdirSync(dst(""))) {
    if (/^sessions-v.+\.json$/.test(f) && f !== sessions) {
      unlinkSync(dst(f))
      console.log(`pruned stale ${f}`)
    }
  }
}
if (!copied) console.warn(`warning: no payloads found in ${src} — site will show its empty state`)
else console.log(`copied ${copied} payload file(s)`)
