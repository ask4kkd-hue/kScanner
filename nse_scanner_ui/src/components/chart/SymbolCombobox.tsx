import { CheckIcon, ChevronsUpDownIcon } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

/** Searchable symbol picker — cmdk filters client-side, fine at 2400 items without virtualization. */
export function SymbolCombobox({
  symbols, value, onChange,
}: {
  symbols: string[]
  value: string
  onChange: (symbol: string) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="w-40 justify-between font-mono-tabular">
          {value || "Select symbol"}
          <ChevronsUpDownIcon className="ml-1 size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-0">
        <Command>
          <CommandInput placeholder="Search symbol…" />
          <CommandList>
            <CommandEmpty>No symbol found.</CommandEmpty>
            <CommandGroup>
              {symbols.map((sym) => (
                <CommandItem
                  key={sym}
                  value={sym}
                  onSelect={(v) => {
                    onChange(v)
                    setOpen(false)
                  }}
                >
                  <CheckIcon className={cn("size-3.5", value === sym ? "opacity-100" : "opacity-0")} />
                  {sym}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
