// Mock MatchApi: no network. Each getJob call waits `delayMs` and returns the next state of the job:
// uploading -> parsing -> matching -> done (the example response). A file named fail*.pdf goes
// uploading -> parsing -> failed, for manual testing of the error view.
import { exampleResponse } from '../data'
import type { JobStatus, MatchApi, MatchResponse } from './types'

export interface MockApiOptions {
  /** Delay before each uploadCv / getJob answer, in ms. 0 in tests. */
  delayMs?: number
  response?: MatchResponse
}

export const MOCK_FAILURE_MESSAGE = 'Could not read the CV (mock failure for files named fail*.pdf).'

const FAIL_NAME = /^fail.*\.pdf$/i

export function isMockFailureName(name: string): boolean {
  return FAIL_NAME.test(name)
}

function wait(ms: number): Promise<void> {
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve()
}

export function createMockApi({ delayMs = 0, response = exampleResponse }: MockApiOptions = {}): MatchApi {
  const jobs = new Map<string, { sequence: JobStatus[]; next: number }>()
  let counter = 0

  return {
    async uploadCv(file) {
      await wait(delayMs)
      counter += 1
      const jobId = `mock-${counter}`
      const sequence: JobStatus[] = isMockFailureName(file.name)
        ? [{ state: 'uploading' }, { state: 'parsing' }, { state: 'failed', error: MOCK_FAILURE_MESSAGE }]
        : [{ state: 'uploading' }, { state: 'parsing' }, { state: 'matching' }, { state: 'done', result: response }]
      jobs.set(jobId, { sequence, next: 0 })
      return { jobId }
    },

    async getJob(jobId) {
      await wait(delayMs)
      const job = jobs.get(jobId)
      if (!job) return { state: 'failed', error: `Unknown job ${jobId}.` }
      const status = job.sequence[Math.min(job.next, job.sequence.length - 1)]
      job.next += 1
      // The sequence is never empty, so status is always set.
      return status as JobStatus
    },
  }
}
