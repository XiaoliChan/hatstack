// Copy the crawled dataset into the site's public dir before dev/build.
// Falls back with a warning (site renders its error state without it).
import { copyFileSync, existsSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const src = resolve(here, "../dataset/dataset.json")
const dst = resolve(here, "public/dataset.json")

if (existsSync(src)) {
  copyFileSync(src, dst)
  console.log(`dataset copied: ${src} -> ${dst}`)
} else {
  console.warn(`warning: ${src} not found — site will show its empty state`)
}
