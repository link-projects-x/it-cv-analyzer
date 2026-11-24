import { useEffect, useReducer, useRef } from 'react'
import { App } from '../App'
import type { MatchApi } from '../api/types'
import { ErrorView } from './ErrorView'
import { flowReducer, initialFlow } from './flow'
import { ProgressView } from './ProgressView'
import { runJob } from './runJob'
import { UploadScreen } from './UploadScreen'
import '../styles/tokens.css'
import './upload.css'

export function AppFlow({
  api,
  pollMs = 0,
  demo = false,
  needsAccessCode = false,
  local = false,
}: {
  api: MatchApi
  pollMs?: number
  demo?: boolean
  needsAccessCode?: boolean
  local?: boolean
}) {
  const [state, dispatch] = useReducer(flowReducer, initialFlow)
  // Id of the run whose callbacks are applied; a newer run or unmount makes older runs stale.
  const runRef = useRef(0)

  useEffect(
    () => () => {
      runRef.current += 1
    },
    [],
  )

  function start(file: File) {
    runRef.current += 1
    const run = runRef.current
    dispatch({ type: 'start', file })
    void runJob(api, file, (status) => dispatch({ type: 'status', status }), {
      pollMs,
      isCancelled: () => runRef.current !== run,
    })
  }

  if (state.screen === 'results') {
    return <App response={state.response} onNewCv={() => dispatch({ type: 'newCv' })} />
  }

  return (
    <div className="up-page">
      <main className="up-main">
        <header className="up-header">
          {local && <span className="up-eyebrow">Free CV analyzer for IT jobs</span>}
          <h1 className="up-h1">{local ? 'See which skills your CV is missing for IT jobs' : 'CV vs DOU AI/ML vacancies'}</h1>
          <p className="up-lead">
            {local
              ? 'Upload your CV. We compare it with the requirements of parsed IT vacancies, show what is covered and what is missing, and let you move sliders to see how coverage and the salary estimate change.'
              : 'Upload a CV to see how it covers the requirements of AI/ML vacancies from DOU, and move sliders to see how coverage and the salary estimate change.'}
          </p>
        </header>
        {state.screen === 'upload' && (
          <UploadScreen
            rejection={state.rejection}
            demo={demo}
            needsAccessCode={needsAccessCode}
            local={local}
            onFile={start}
            onReject={(message) => dispatch({ type: 'rejected', message })}
          />
        )}
        {state.screen === 'progress' && <ProgressView fileName={state.file.name} step={state.step} />}
        {state.screen === 'error' && (
          <ErrorView
            fileName={state.file.name}
            message={state.message}
            onRetry={() => start(state.file)}
            onOtherFile={() => dispatch({ type: 'newCv' })}
          />
        )}
      </main>
    </div>
  )
}
