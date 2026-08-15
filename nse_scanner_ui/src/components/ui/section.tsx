import * as React from "react"

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { cn } from "@/lib/utils"

/** Direct port of web/components.py's section() — a collapsible panel with the same default-open behavior. */
export function Section({
  title,
  collapsed = false,
  className,
  children,
}: {
  title: string
  collapsed?: boolean
  className?: string
  children: React.ReactNode
}) {
  return (
    <Accordion
      type="single"
      collapsible
      defaultValue={collapsed ? undefined : "item"}
      className={cn("rounded-lg border border-border bg-card px-4", className)}
    >
      <AccordionItem value="item" className="border-b-0">
        <AccordionTrigger className="text-base">{title}</AccordionTrigger>
        <AccordionContent>{children}</AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}

export function PageTitle({ text, subtitle }: { text: string; subtitle?: string }) {
  return (
    <div className="mb-2 flex flex-col gap-0">
      <h1 className="text-lg font-semibold">{text}</h1>
      {subtitle && <p className="text-muted-foreground text-sm">{subtitle}</p>}
    </div>
  )
}
