// HTTP MatchApi for services/api (POST /uploads, GET /jobs/{id}); see services/api/api/http.py for the shapes.
// Every call carries `Authorization: Bearer <access code>`. Errors from the API ({error, message}) are thrown with the
// API's message, so runJob shows it in the error view.
import type { JobStatus, MatchApi } from './types'

/** VITE_API_URL, read once at module load. Unset or blank -> null, and the app uses the mock. */
export const API_URL: string | null = normalizeApiUrl(import.meta.env.VITE_API_URL)

export function normalizeApiUrl(value: string | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed.replace(/\/+$/, '') : null
}

export const MISSING_CODE_MESSAGE = 'Enter your access code first.'
export const INVALID_CODE_MESSAGE = 'The access code is not valid.'
export const UPLOAD_FAILED_MESSAGE = 'The file could not be uploaded. Try again.'

type Fetch = typeof fetch

interface UploadTicket {
  job_id: string
  upload: { url: string; fields: Record<string, string> }
}

async function apiError(res: Response): Promise<Error> {
  if (res.status === 401) return new Error(INVALID_CODE_MESSAGE)
  try {
    const body = (await res.json()) as { message?: unknown }
    if (typeof body.message === 'string' && body.message) return new Error(body.message)
  } catch {
    // not JSON
  }
  return new Error(`Request failed (${res.status}).`)
}

export function createHttpApi(baseUrl: string, getAccessCode: () => string, fetchImpl: Fetch = fetch): MatchApi {
  function authHeaders(): Record<string, string> {
    const code = getAccessCode().trim()
    if (!code) throw new Error(MISSING_CODE_MESSAGE)
    return { Authorization: `Bearer ${code}` }
  }

  return {
    async uploadCv(file: File) {
      const res = await fetchImpl(`${baseUrl}/uploads`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, size: file.size, content_type: file.type }),
      })
      if (!res.ok) throw await apiError(res)
      const ticket = (await res.json()) as UploadTicket

      // S3 presigned POST: every policy field first, the file last under the name "file".
      const form = new FormData()
      for (const [name, value] of Object.entries(ticket.upload.fields)) form.append(name, value)
      form.append('file', file)
      const s3 = await fetchImpl(ticket.upload.url, { method: 'POST', body: form })
      if (!s3.ok) throw new Error(UPLOAD_FAILED_MESSAGE)
      return { jobId: ticket.job_id }
    },

    async getJob(jobId: string): Promise<JobStatus> {
      const res = await fetchImpl(`${baseUrl}/jobs/${encodeURIComponent(jobId)}`, { headers: authHeaders() })
      if (!res.ok) throw await apiError(res)
      return (await res.json()) as JobStatus
    },
  }
}
