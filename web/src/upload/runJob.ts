import type { JobStatus, MatchApi } from '../api/types'

export interface RunJobOptions {
  /** Pause between getJob calls while the job is not finished, in ms. */
  pollMs: number
  /** Checked after every await; true stops the run without further callbacks. */
  isCancelled: () => boolean
}

function wait(ms: number): Promise<void> {
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve()
}

/**
 * Uploads the file and polls the job. Calls onStatus with "uploading" first, then with every status
 * getJob returns, ending with "done" or "failed". A rejected API call is reported as "failed".
 */
export async function runJob(
  api: MatchApi,
  file: File,
  onStatus: (status: JobStatus) => void,
  { pollMs, isCancelled }: RunJobOptions,
): Promise<void> {
  try {
    onStatus({ state: 'uploading' })
    const { jobId } = await api.uploadCv(file)
    for (;;) {
      if (isCancelled()) return
      const status = await api.getJob(jobId)
      if (isCancelled()) return
      onStatus(status)
      if (status.state === 'done' || status.state === 'failed') return
      await wait(pollMs)
    }
  } catch (err) {
    if (isCancelled()) return
    onStatus({ state: 'failed', error: err instanceof Error ? err.message : String(err) })
  }
}
