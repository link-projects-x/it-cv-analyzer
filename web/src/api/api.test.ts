import { describe, expect, it } from 'vitest'
import { exampleResponse } from '../data'
import { createHttpApi, INVALID_CODE_MESSAGE, MISSING_CODE_MESSAGE, normalizeApiUrl, UPLOAD_FAILED_MESSAGE } from './http'
import { HTTP_POLL_MS, pickApi } from './index'
import { createMockApi, isMockFailureName, MOCK_FAILURE_MESSAGE } from './mock'
import type { JobStatus, MatchApi } from './types'

const cv = (name: string) => new File(['text'], name)

async function states(api: MatchApi, jobId: string, calls: number): Promise<JobStatus[]> {
  const out: JobStatus[] = []
  for (let i = 0; i < calls; i++) out.push(await api.getJob(jobId))
  return out
}

describe('mock MatchApi', () => {
  it('walks uploading -> parsing -> matching -> done with the example response', async () => {
    const api = createMockApi({ delayMs: 0 })
    const { jobId } = await api.uploadCv(cv('cv.pdf'))
    const seq = await states(api, jobId, 5)
    expect(seq.map((s) => s.state)).toEqual(['uploading', 'parsing', 'matching', 'done', 'done'])
    const done = seq[3]
    expect(done?.state === 'done' && done.result).toBe(exampleResponse)
  })

  it('fail*.pdf goes uploading -> parsing -> failed', async () => {
    const api = createMockApi({ delayMs: 0 })
    const { jobId } = await api.uploadCv(cv('fail-cv.pdf'))
    const seq = await states(api, jobId, 4)
    expect(seq.map((s) => s.state)).toEqual(['uploading', 'parsing', 'failed', 'failed'])
    expect(seq[2]).toEqual({ state: 'failed', error: MOCK_FAILURE_MESSAGE })
  })

  it('matches only fail*.pdf names', () => {
    expect(isMockFailureName('fail.pdf')).toBe(true)
    expect(isMockFailureName('FAIL-me.PDF')).toBe(true)
    expect(isMockFailureName('fail.docx')).toBe(false)
    expect(isMockFailureName('cv-fail.pdf')).toBe(false)
  })

  it('gives each upload its own job', async () => {
    const api = createMockApi({ delayMs: 0 })
    const a = await api.uploadCv(cv('a.pdf'))
    const b = await api.uploadCv(cv('b.pdf'))
    expect(a.jobId).not.toBe(b.jobId)
    await states(api, a.jobId, 2)
    expect((await api.getJob(b.jobId)).state).toBe('uploading')
  })

  it('reports an unknown job as failed', async () => {
    const api = createMockApi({ delayMs: 0 })
    expect(await api.getJob('nope')).toEqual({ state: 'failed', error: 'Unknown job nope.' })
  })
})

interface Call {
  url: string
  init: RequestInit | undefined
}

function fakeFetch(responses: Response[]) {
  const calls: Call[] = []
  const impl = (async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init })
    const next = responses.shift()
    if (!next) throw new Error('unexpected fetch')
    return next
  }) as typeof fetch
  return { impl, calls }
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const ticket = {
  job_id: '6f1c2b9e-3d4a-4f7b-9a10-2c5e8d7b1a01',
  upload: { url: 'https://bucket.s3.test/', fields: { key: 'cv/x.pdf', 'Content-Type': 'application/pdf', policy: 'p' } },
  expires_in: 600,
}

describe('HTTP MatchApi', () => {
  const pdf = () => new File(['%PDF'], 'cv.pdf', { type: 'application/pdf' })

  it('uploadCv: POST /uploads with the code, then the S3 form with the file last', async () => {
    const { impl, calls } = fakeFetch([json(201, ticket), new Response(null, { status: 204 })])
    const api = createHttpApi('https://api.test', () => ' code-1 ', impl)
    await expect(api.uploadCv(pdf())).resolves.toEqual({ jobId: ticket.job_id })

    expect(calls[0]?.url).toBe('https://api.test/uploads')
    expect(calls[0]?.init?.method).toBe('POST')
    expect((calls[0]?.init?.headers as Record<string, string>).Authorization).toBe('Bearer code-1')
    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({ filename: 'cv.pdf', size: 4, content_type: 'application/pdf' })

    expect(calls[1]?.url).toBe(ticket.upload.url)
    const form = calls[1]?.init?.body as FormData
    expect([...form.keys()]).toEqual(['key', 'Content-Type', 'policy', 'file'])
    expect((calls[1]?.init?.headers as Record<string, string> | undefined)?.Authorization).toBeUndefined()
  })

  it('getJob sends the code and returns the status', async () => {
    const { impl, calls } = fakeFetch([json(200, { state: 'parsing' })])
    const api = createHttpApi('https://api.test', () => 'code-1', impl)
    await expect(api.getJob(ticket.job_id)).resolves.toEqual({ state: 'parsing' })
    expect(calls[0]?.url).toBe(`https://api.test/jobs/${ticket.job_id}`)
    expect((calls[0]?.init?.headers as Record<string, string>).Authorization).toBe('Bearer code-1')
  })

  it('no code: rejects before any request', async () => {
    const { impl, calls } = fakeFetch([])
    const api = createHttpApi('https://api.test', () => '  ', impl)
    await expect(api.uploadCv(pdf())).rejects.toThrow(MISSING_CODE_MESSAGE)
    await expect(api.getJob('j')).rejects.toThrow(MISSING_CODE_MESSAGE)
    expect(calls).toHaveLength(0)
  })

  it('401 -> invalid code message; other errors -> the API message', async () => {
    const { impl } = fakeFetch([
      json(401, { error: 'unauthorized', message: 'A valid access code is required.' }),
      json(429, { error: 'daily_limit', message: 'This access code has used its 10 uploads for today (UTC).' }),
      new Response('oops', { status: 500 }),
    ])
    const api = createHttpApi('https://api.test', () => 'c', impl)
    await expect(api.uploadCv(pdf())).rejects.toThrow(INVALID_CODE_MESSAGE)
    await expect(api.uploadCv(pdf())).rejects.toThrow('used its 10 uploads')
    await expect(api.getJob('j')).rejects.toThrow('Request failed (500).')
  })

  it('S3 rejecting the file -> upload failed message', async () => {
    const { impl } = fakeFetch([json(201, ticket), new Response('<Error/>', { status: 403 })])
    const api = createHttpApi('https://api.test', () => 'c', impl)
    await expect(api.uploadCv(pdf())).rejects.toThrow(UPLOAD_FAILED_MESSAGE)
  })
})

describe('API selection', () => {
  it('unset or blank VITE_API_URL means mock; trailing slashes are dropped', () => {
    expect(normalizeApiUrl(undefined)).toBeNull()
    expect(normalizeApiUrl('  ')).toBeNull()
    expect(normalizeApiUrl(' https://x.test/ ')).toBe('https://x.test')
  })

  it('pickApi: null -> mock (demo, no poll pause), URL -> HTTP API', async () => {
    const mock = pickApi(null, 0)
    expect(mock.demo).toBe(true)
    expect(mock.pollMs).toBe(0)
    await expect(mock.api.uploadCv(cv('cv.pdf'))).resolves.toEqual({ jobId: 'mock-1' })

    const http = pickApi('https://x.test')
    expect(http.demo).toBe(false)
    expect(http.pollMs).toBe(HTTP_POLL_MS)
  })
})
