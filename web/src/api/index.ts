import { readAccessCode } from './accessCode'
import { API_URL, createHttpApi } from './http'
import { createMockApi } from './mock'
import { createLocalApi } from '../local/localApi'
import type { MatchApi } from './types'

/** Delay of each mock step in the running app, so the progress view is visible. */
export const MOCK_DELAY_MS = 1200
/** Pause between getJob calls for the HTTP API. The mock waits inside getJob, so it polls without a pause. */
export const HTTP_POLL_MS = 2000

export interface ApiConfig {
  api: MatchApi
  pollMs: number
  demo: boolean
  needsAccessCode: boolean
  local: boolean
}

/** VITE_API_MODE=local reads and matches the CV in the browser (static site); otherwise the HTTP API when
 * VITE_API_URL is set, else the mock with the example response. */
export function pickApi(apiUrl: string | null, mockDelayMs = MOCK_DELAY_MS, mode?: string): ApiConfig {
  if (mode === 'local') return { api: createLocalApi(), pollMs: 300, demo: false, needsAccessCode: false, local: true }
  const picked = apiUrl === null
    ? { api: createMockApi({ delayMs: mockDelayMs }), pollMs: 0, demo: true }
    : { api: createHttpApi(apiUrl, readAccessCode), pollMs: HTTP_POLL_MS, demo: false }
  return { ...picked, needsAccessCode: !picked.demo, local: false }
}

export const apiConfig = pickApi(API_URL, MOCK_DELAY_MS, import.meta.env.VITE_API_MODE)
