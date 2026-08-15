import { useVirtualizer } from "@tanstack/react-virtual"
import { CheckIcon, ChevronsUpDownIcon } from "lucide-react"
import { useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

const ROW_HEIGHT = 32

/**
 * Virtualized symbol picker. Previously used cmdk's <Command>, which mounts
 * and indexes every item up front — at ~2400 symbols that's a real, felt
 * delay opening the popover. Filtering 2400 strings is cheap; rendering
 * 2400 DOM nodes at once is not. Only the ~10 visible rows render now,
 * regardless of universe size.
 */
export function SymbolCombobox({
  symbols, value, onChange,
}: {
  symbols: string[]
  value: string
  onChange: (symbol: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    if (!query) return symbols
    const q = query.toUpperCase()
    return symbols.filter((s) => s.includes(q))
  }, [symbols, query])

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })

  const select = (sym: string) => {
    onChange(sym)
    setOpen(false)
    setQuery("")
  }

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQuery("") }}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="w-40 justify-between font-mono-tabular">
          {value || "Select symbol"}
          <ChevronsUpDownIcon className="ml-1 size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-0">
        <div className="border-b border-border p-1">
          {/* eslint-disable-next-line jsx-a11y/no-autofocus -- popover just opened, this is the whole point of it */}
          <input
            autoFocus
            placeholder="Search symbol…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && filtered.length > 0) select(filtered[0])
            }}
            className="h-8 w-full bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div ref={scrollRef} className="max-h-72 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-muted-foreground p-3 text-center text-sm">No symbol found.</p>
          ) : (
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {virtualizer.getVirtualItems().map((item) => {
                const sym = filtered[item.index]
                return (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => select(sym)}
                    style={{
                      position: "absolute", top: 0, left: 0, width: "100%",
                      height: item.size, transform: `translateY(${item.start}px)`,
                    }}
                    className={cn(
                      "flex items-center gap-2 px-2 text-sm hover:bg-accent",
                      value === sym && "bg-accent"
                    )}
                  >
                    <CheckIcon className={cn("size-3.5 shrink-0", value === sym ? "opacity-100" : "opacity-0")} />
                    {sym}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
