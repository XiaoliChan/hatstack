import { useEffect, useRef } from "react"

export function SearchBox({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== ref.current) {
        e.preventDefault()
        ref.current?.focus()
      }
      if (e.key === "Escape" && document.activeElement === ref.current) {
        ref.current?.blur()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <div className="relative">
      <input
        ref={ref}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search briefings, speakers, topics…"
        aria-label="Search briefings"
        className="w-full bg-transparent border-b border-line focus:border-foreground transition-colors text-2xl md:text-[32px] font-medium py-3 pr-14 placeholder:text-muted-foreground/50 outline-none [::-webkit-search-cancel-button]:hidden"
      />
      <kbd className="absolute right-1 top-1/2 -translate-y-1/2 select-none border border-line rounded px-2 py-0.5 text-xs text-muted-foreground hidden md:block">
        /
      </kbd>
    </div>
  )
}
