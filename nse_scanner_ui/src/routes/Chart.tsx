import { useParams } from "react-router-dom"

import { ChartPanel } from "@/components/chart/ChartPanel"
import { PageTitle } from "@/components/ui/section"

export default function Chart() {
  const { symbol } = useParams<{ symbol?: string }>()

  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col gap-2">
      <PageTitle text="Chart" />
      <div className="min-h-0 flex-1">
        <ChartPanel initialSymbol={symbol} />
      </div>
    </div>
  )
}
