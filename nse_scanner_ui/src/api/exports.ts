import { api } from "./client"

export const exportsApi = {
  reveal: () => api.post<{ path: string; opened: boolean }>("/api/exports/reveal"),
}
