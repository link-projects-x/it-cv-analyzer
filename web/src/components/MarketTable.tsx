import { levelName } from '../contracts'
import type { MarketRow } from '../market'

const STATUS_TEXT = { covered: 'enough years', partial: 'fewer years than typical', missing: 'not in the profile' }

export function MarketTable({ rows, total }: { rows: MarketRow[]; total: number }) {
  if (rows.length === 0) return null
  return (
    <section className="card market" aria-labelledby="market-h">
      <h2 id="market-h" className="section-h">
        What these vacancies require
      </h2>
      <p className="section-sub">
        Required skills across {total} vacancies, gaps first. Typical years: the median the vacancies ask for.
      </p>
      <div className="market-scroll">
        <table className="market-table">
          <thead>
            <tr>
              <th scope="col">Skill</th>
              <th scope="col" className="num">Required in</th>
              <th scope="col" className="num">Typical years</th>
              <th scope="col" className="num">You</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className={`market-${r.status}`} data-status={r.status}>
                <th scope="row">
                  <span className="market-mark" aria-hidden="true" />
                  {r.label}
                  <span className="sr-only">: {STATUS_TEXT[r.status]}</span>
                </th>
                <td className="num">{Math.round(r.share * 100)}%</td>
                <td className="num">{levelName(r.medianYears)}</td>
                <td className="num">{levelName(r.years)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
