import { create } from "zustand"
import { persist } from "zustand/middleware"

/**
 * Purely cosmetic client state — nav drawer collapse. In NiceGUI this round-
 * tripped to the `ui_prefs` DB table (get_pref/set_pref in shell.py); here
 * it's localStorage via zustand's persist middleware instead, since it's
 * client-only preference with no reason to touch the server.
 */
export type L1L2LineStyle = "solid" | "dashed" | "dotted"

export type Theme = "black" | "terminal-green" | "kite-slate" | "oled-black" | "slate-blue"

export const THEME_LABELS: Record<Theme, string> = {
  black: "Black (default)",
  "terminal-green": "Terminal green",
  "kite-slate": "Kite-style slate-teal",
  "oled-black": "High-contrast OLED black",
  "slate-blue": "Slate-blue professional",
}

interface UiPrefsState {
  navCollapsed: boolean
  toggleNav: () => void
  // L1/L2/neckline marker style on the Chart screen — a single-timeframe
  // override only; D/W/M-together mode keeps its fixed per-timeframe
  // colors so the three timeframes stay visually distinguishable.
  l1l2Color: string
  l1l2LineStyle: L1L2LineStyle
  l1l2LineWidth: number
  setL1L2Style: (patch: Partial<Pick<UiPrefsState, "l1l2Color" | "l1l2LineStyle" | "l1l2LineWidth">>) => void
  theme: Theme
  setTheme: (theme: Theme) => void
}

export const useUiPrefs = create<UiPrefsState>()(
  persist(
    (set) => ({
      navCollapsed: false,
      toggleNav: () => set((s) => ({ navCollapsed: !s.navCollapsed })),
      l1l2Color: "#D9A030",
      l1l2LineStyle: "dashed",
      l1l2LineWidth: 1,
      setL1L2Style: (patch) => set(patch),
      theme: "black",
      setTheme: (theme) => set({ theme }),
    }),
    { name: "kscanner-ui-prefs" }
  )
)
