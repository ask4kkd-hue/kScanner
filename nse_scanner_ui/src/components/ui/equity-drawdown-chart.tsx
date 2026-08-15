import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"

/** Full equity curve + drawdown chart — shared by Performance and Dashboard. */
export function EquityDrawdownChart({
  data,
}: {
  data: { exit_date: string; cum_pnl: number; drawdown?: number }[]
}) {
  if (data.length === 0) return <p className="text-muted-foreground text-sm">No closed trades yet.</p>
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="exit_date" tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
        <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            background: "var(--color-card)", border: "1px solid var(--color-border)", fontSize: 12,
          }}
        />
        <Area
          type="monotone" dataKey="drawdown" stroke="none"
          fill="var(--color-destructive)" fillOpacity={0.15}
        />
        <Line type="monotone" dataKey="cum_pnl" stroke="var(--color-primary)" strokeWidth={2} dot={false} name="Cumulative P&L" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
