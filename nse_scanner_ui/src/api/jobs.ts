import { api } from "./client"

export interface JobStatus {
  job_id: string
  status: "pending" | "running" | "done" | "error"
  step: string | null
  error: string | null
}

export const jobsApi = {
  startFullRebuild: () => api.post<{ job_id: string }>("/api/jobs/full-rebuild"),
  get: (jobId: string) => api.get<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`),
}
