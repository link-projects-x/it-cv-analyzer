import type { Summary, SummaryDelta } from '../summary'
import { Delta } from './Delta'
import { SalaryCard } from './SalaryPanel'

export function StatCards({
  current,
  delta,
  touched,
  modelVersion,
}: {
  current: Summary
  delta: SummaryDelta
  touched: boolean
  modelVersion: string
}) {
  const atOpening = <span className="stat-delta-none">as in the CV</span>
  return (
    <section className="stats" aria-label="Summary">
      <article className="card stat" data-testid="stat-fits">
        <h2 className="stat-label">Fits</h2>
        <p className="stat-value num">
          {current.fits}
          <span className="stat-unit"> of {current.total}</span>
        </p>
        <p className="stat-delta">{touched ? <><Delta value={delta.fits} /> vs opening</> : atOpening}</p>
      </article>
      <article className="card stat" data-testid="stat-mean">
        <h2 className="stat-label">Mean coverage</h2>
        <p className="stat-value num">{(current.mean * 100).toFixed(1)}%</p>
        <p className="stat-delta">
          {touched ? <><Delta value={delta.meanPp} digits={1} unit="pp" /> vs opening</> : atOpening}
        </p>
      </article>
      <SalaryCard estimate={current.salary} delta={touched ? delta.salary : undefined} modelVersion={modelVersion} />
    </section>
  )
}
