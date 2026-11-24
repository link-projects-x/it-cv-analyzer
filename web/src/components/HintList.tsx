import type { Hint } from '../hints'
import { Delta } from './Delta'

export function HintList({ hints }: { hints: Hint[] }) {
  return (
    <section className="card hints-card" aria-labelledby="hints-h">
      <h2 id="hints-h" className="section-h">Next steps</h2>
      <p className="section-sub">Effect of one step up on one slider, from the current settings.</p>
      {hints.length === 0 ? (
        <p className="muted">No single step up changes fits, coverage or salary.</p>
      ) : (
        <ol className="hints">
          {hints.map((h) => (
            <li key={h.key} className="hint">
              <span className="sr-only">{h.text}.</span>
              <span className="hint-what" aria-hidden="true">
                <strong>{h.label}</strong>{' '}
                <span className="hint-step">
                  {h.from} → {h.to}
                </span>
              </span>
              <span className="hint-effects" aria-hidden="true">
                <span className="hint-effect">
                  <Delta value={h.fitsDelta} unit={Math.abs(h.fitsDelta) === 1 ? 'vacancy fits' : 'vacancies fit'} />
                </span>
                <span className="hint-effect">
                  <Delta value={h.coverageDeltaPp} digits={1} unit="pp mean coverage" />
                </span>
                {h.salaryDelta !== null && (
                  <span className="hint-effect">
                    <Delta value={h.salaryDelta} unit="USD/month" />
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
