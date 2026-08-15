import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

export function DistributionChart({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data).map(([name, count]) => ({ name, count }))
  if (rows.length === 0) return null
  return (
    <div className="mt-2">
      <p className="mb-1 text-sm font-semibold">Where the second bottom formed</p>
      <BarChart width={480} height={220} data={rows}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="name" tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
        <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
        <Bar dataKey="count" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </div>
  )
}
