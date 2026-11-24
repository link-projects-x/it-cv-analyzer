import { levelName } from '../contracts'
import type { Plan } from '../plan'
import type { Summary, SummaryDelta } from '../summary'
import { Delta } from './Delta'

function salaryText(s: Summary['salary']): string | null {
  if (s.kind === 'none') return null
  const v = `${Math.round(s.value).toLocaleString('en-US')} USD/month`
  if (s.kind === 'point' && s.low !== null && s.high !== null) {
    return `${v} (${Math.round(s.low).toLocaleString('en-US')}–${Math.round(s.high).toLocaleString('en-US')})`
  }
  return v
}

export function Headline({
  current,
  delta,
  touched,
  plan,
  modelVersion,
}: {
  current: Summary
  delta: SummaryDelta
  touched: boolean
  plan: Plan
  modelVersion: string
}) {
  const salary = salaryText(current.salary)
  return (
    <section className="card headline" aria-label="Summary">
      <p className="headline-main">
        You fit{' '}
        <strong className="num" data-testid="headline-fits">
          {current.fits} of {current.total}
        </strong>{' '}
        vacancies
        {touched && (
          <>
            {' '}
            <Delta value={delta.fits} />
          </>
        )}
        <span className="headline-sep"> · </span>
        mean coverage{' '}
        <strong className="num" data-testid="stat-mean">
          {(current.mean * 100).toFixed(0)}%
          {touched && (
            <>
              {' '}
              <Delta value={delta.meanPp} digits={1} unit="pp" />
            </>
          )}
        </strong>
        {salary && (
          <>
            <span className="headline-sep"> · </span>
            salary estimate <strong className="num">{salary}</strong>
          </>
        )}
      </p>
      {plan.steps.length > 0 && (
        <p className="headline-plan" data-testid="headline-plan">
          {plan.steps
            .map((s) => `${s.name} ${levelName(s.from)} → ${levelName(s.to)}`)
            .join(', ')}
          {plan.fitsAfter > plan.fitsBefore
            ? ` would make it ${plan.fitsAfter} of ${current.total}.`
            : ': the largest coverage gains, no new full fits.'}
        </p>
      )}
      {salary && (
        <p className="headline-note">
          Skill sliders do not change the salary estimate: the salary model has no skill inputs. Model: {modelVersion}
        </p>
      )}
    </section>
  )
}
