import { create } from "zustand"
import { persist } from "zustand/middleware"

/**
 * Purely cosmetic client state — nav drawer collapse. In NiceGUI this round-
 * tripped to the `ui_prefs` DB table (get_pref/set_pref in shell.py); here
 * it's localStorage via zustand's persist middleware instead, since it's
 * client-only preference with no reason to touch the server.
 */
interface UiPrefsState {
  navCollapsed: boolean
  toggleNav: () => void
}

export const useUiPrefs = create<UiPrefsState>()(
  persist(
    (set) => ({
      navCollapsed: false,
      toggleNav: () => set((s) => ({ navCollapsed: !s.navCollapsed })),
    }),
    { name: "kscanner-ui-prefs" }
  )
)
