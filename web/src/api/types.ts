// API between the page and the backend: upload a CV, then poll the job until it is done or failed.
// MatchResponse is the hand-written type of contracts/match-response.schema.json; it lives in src/types.ts
// together with the other contract types, and is re-exported here.
import type { MatchResponse } from '../types'

export type { MatchResponse }

/** Job states before the result is ready, in the order the progress view shows them. */
export type JobStep = 'uploading' | 'parsing' | 'matching'

export const JOB_STEPS: readonly JobStep[] = ['uploading', 'parsing', 'matching']

export type JobStatus =
  | { state: JobStep }
  | { state: 'done'; result: MatchResponse }
  | { state: 'failed'; error: string }

export interface MatchApi {
  uploadCv(file: File): Promise<{ jobId: string }>
  getJob(jobId: string): Promise<JobStatus>
}
