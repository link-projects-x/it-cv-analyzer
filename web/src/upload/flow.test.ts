import { describe, expect, it } from 'vitest'
import { createMockApi } from '../api/mock'
import type { JobStatus, MatchApi } from '../api/types'
import { exampleResponse } from '../data'
import { flowReducer, initialFlow, type FlowState } from './flow'
import { runJob } from './runJob'

const file = new File(['text'], 'cv.pdf')

describe('flowReducer', () => {
  it('upload -> progress -> results', () => {
    let s: FlowState = flowReducer(initialFlow, { type: 'start', file })
    expect(s).toEqual({ screen: 'progress', file, step: 'uploading' })
    s = flowReducer(s, { type: 'status', status: { state: 'parsing' } })
    expect(s).toEqual({ screen: 'progress', file, step: 'parsing' })
    s = flowReducer(s, { type: 'status', status: { state: 'done', result: exampleResponse } })
    expect(s).toEqual({ screen: 'results', response: exampleResponse })
    expect(flowReducer(s, { type: 'newCv' })).toEqual(initialFlow)
  })

  it('failed -> error, Retry (start) from error -> progress with the same file', () => {
    const progress = flowReducer(initialFlow, { type: 'start', file })
    const error = flowReducer(progress, { type: 'status', status: { state: 'failed', error: 'boom' } })
    expect(error).toEqual({ screen: 'error', file, message: 'boom' })
    expect(flowReducer(error, { type: 'start', file })).toEqual({ screen: 'progress', file, step: 'uploading' })
  })

  it('rejection shows on upload and clears on the next start', () => {
    const rejected = flowReducer(initialFlow, { type: 'rejected', message: 'x is not a PDF, DOCX or TXT file.' })
    expect(rejected).toEqual({ screen: 'upload', rejection: 'x is not a PDF, DOCX or TXT file.' })
    expect(flowReducer(rejected, { type: 'start', file }).screen).toBe('progress')
  })

  it('ignores statuses outside progress and starts during progress', () => {
    const done: JobStatus = { state: 'done', result: exampleResponse }
    expect(flowReducer(initialFlow, { type: 'status', status: done })).toBe(initialFlow)
    const progress = flowReducer(initialFlow, { type: 'start', file })
    expect(flowReducer(progress, { type: 'start', file: new File(['x'], 'b.pdf') })).toBe(progress)
  })
})

describe('runJob', () => {
  it('reports uploading, then every mock status up to done', async () => {
    const seen: string[] = []
    await runJob(createMockApi({ delayMs: 0 }), file, (s) => seen.push(s.state), { pollMs: 0, isCancelled: () => false })
    expect(seen).toEqual(['uploading', 'uploading', 'parsing', 'matching', 'done'])
  })

  it('turns a rejected call into failed with its message', async () => {
    const api: MatchApi = {
      uploadCv: () => Promise.reject(new Error('network down')),
      getJob: () => Promise.reject(new Error('unreachable')),
    }
    const seen: JobStatus[] = []
    await runJob(api, file, (s) => seen.push(s), { pollMs: 0, isCancelled: () => false })
    expect(seen).toEqual([{ state: 'uploading' }, { state: 'failed', error: 'network down' }])
  })

  it('stops without callbacks once cancelled', async () => {
    let cancelled = false
    const seen: string[] = []
    await runJob(
      createMockApi({ delayMs: 0 }),
      file,
      (s) => {
        seen.push(s.state)
        if (s.state === 'parsing') cancelled = true
      },
      { pollMs: 0, isCancelled: () => cancelled },
    )
    expect(seen).toEqual(['uploading', 'uploading', 'parsing'])
  })
})
