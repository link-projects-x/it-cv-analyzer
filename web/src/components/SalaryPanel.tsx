import type { SalaryEstimate } from '../state'
import { Delta } from './Delta'

function usd(n: number): string {
  return `${Math.round(n).toLocaleString('en-US')} USD`
}

// Salary stat card. `delta` is undefined at the opening state and null when the estimate is a dash.
export function SalaryCard({
  estimate,
  delta,
  modelVersion,
}: {
  estimate: SalaryEstimate
  delta?: number | null
  modelVersion: string
}) {
  let main: string
  let range: string | null = null
  let note: string | null = null
  switch (estimate.kind) {
    case 'point':
      main = usd(estimate.value)
      if (estimate.low !== null && estimate.high !== null) range = `${usd(estimate.low)} – ${usd(estimate.high)}`
      break
    case 'grid':
      main = usd(estimate.value)
      note = `estimate for the new ${estimate.input === 'english' ? 'English level' : 'experience'}, other inputs unchanged`
      break
    case 'none':
      main = '—'
      note =
        estimate.reason === 'two-settings'
          ? 'salary estimate changes one setting at a time'
          : 'the salary model has no estimate for this position'
      break
  }
  return (
    <article className="card stat stat-salary" data-testid="stat-salary">
      <h2 className="stat-label">Salary estimate</h2>
      <p className="stat-value num" data-testid="salary-value">
        {main} {estimate.kind !== 'none' && <span className="stat-unit">/ month</span>}
      </p>
      {range && <p className="stat-range num">{range}</p>}
      <p className="stat-delta">
        {delta === undefined ? (
          <span className="stat-delta-none">as in the CV</span>
        ) : delta === null ? (
          <span className="stat-delta-none">no change shown</span>
        ) : (
          <>
            <Delta value={delta} unit="USD" /> vs opening
          </>
        )}
      </p>
      {note && <p className="stat-note">{note}</p>}
      <p className="stat-foot">
        Skill sliders do not change the salary estimate: the salary model has no skill inputs. Model: {modelVersion}
      </p>
    </article>
  )
}
