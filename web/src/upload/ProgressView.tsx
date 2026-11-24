import { JOB_STEPS, type JobStep } from '../api/types'

const STEP_LABELS: Record<JobStep, string> = {
  uploading: 'Uploading the file',
  parsing: 'Reading skills from the CV',
  matching: 'Matching against vacancies',
}

export function ProgressView({ fileName, step }: { fileName: string; step: JobStep }) {
  const current = JOB_STEPS.indexOf(step)
  return (
    <section className="up-card" aria-labelledby="progress-h">
      <h2 id="progress-h" className="up-h2">
        Analyzing your CV
      </h2>
      <p className="up-file">{fileName}</p>
      <ol className="up-steps">
        {JOB_STEPS.map((s, i) => {
          const status = i < current ? 'done' : i === current ? 'current' : 'pending'
          return (
            <li
              key={s}
              className={`up-step up-step--${status}`}
              aria-current={status === 'current' ? 'step' : undefined}
              data-status={status}
            >
              <span className="up-step-mark" aria-hidden="true">
                {status === 'done' ? '✓' : i + 1}
              </span>
              <span className="up-step-label">{STEP_LABELS[s]}</span>
              <span className="up-visually-hidden">
                {status === 'done' ? ' (done)' : status === 'current' ? ' (in progress)' : ''}
              </span>
            </li>
          )
        })}
      </ol>
      <p className="up-visually-hidden" role="status">
        {STEP_LABELS[step]}
      </p>
    </section>
  )
}
