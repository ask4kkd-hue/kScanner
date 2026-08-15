export default function Placeholder({ screen, phase }: { screen: string; phase: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h1 className="text-lg font-semibold">{screen}</h1>
      <p className="text-muted-foreground text-sm">Coming in {phase} — not built yet.</p>
    </div>
  )
}
