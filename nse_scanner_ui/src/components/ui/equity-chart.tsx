import { Line, LineChart, ResponsiveContainer } from "recharts"

/** Minimal equity-curve sparkline — the Today screen's mini version (no axes/tooltip). */
export function EquitySparkline({ data }: { data: { exit_date: string; cum_pnl: number }[] }) {
  if (data.length === 0) return null
  return (
    <ResponsiveContainer width="100%" height={60}>
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="cum_pnl"
          stroke="var(--color-primary)"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
