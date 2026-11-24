// Screen state machine: upload -> progress -> results, or progress -> error -> (Retry) progress.
// "New CV" on the results screen goes back to upload.
import type { JobStatus, JobStep, MatchResponse } from '../api/types'

export type FlowState =
  | { screen: 'upload'; rejection: string | null }
  | { screen: 'progress'; file: File; step: JobStep }
  | { screen: 'error'; file: File; message: string }
  | { screen: 'results'; response: MatchResponse }

export type FlowEvent =
  | { type: 'rejected'; message: string }
  | { type: 'start'; file: File }
  | { type: 'status'; status: JobStatus }
  | { type: 'newCv' }

export const initialFlow: FlowState = { screen: 'upload', rejection: null }

export function flowReducer(state: FlowState, event: FlowEvent): FlowState {
  switch (event.type) {
    case 'rejected':
      return state.screen === 'upload' ? { screen: 'upload', rejection: event.message } : state
    case 'start':
      return state.screen === 'upload' || state.screen === 'error'
        ? { screen: 'progress', file: event.file, step: 'uploading' }
        : state
    case 'status': {
      if (state.screen !== 'progress') return state
      const s = event.status
      if (s.state === 'done') return { screen: 'results', response: s.result }
      if (s.state === 'failed') return { screen: 'error', file: state.file, message: s.error }
      return { ...state, step: s.state }
    }
    case 'newCv':
      return initialFlow
  }
}
