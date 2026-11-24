import { levelName, shortLevelName, skillName } from '../contracts'
import type { CheckStatus, RequirementCheck } from '../requirements'
import type { Vacancy } from '../types'
import { sortVacancyRows, type VacancyRow } from '../vacancies'
import { CoverageRing } from './CoverageRing'
import { Delta } from './Delta'

export interface VacancyDetails {
  location: Vacancy['location'] | null
  checks: RequirementCheck[]
}

const STATUS_TEXT: Record<CheckStatus, string> = {
  covered: 'covered',
  partial: 'partly covered',
  missing: 'missing',
}

function locationText(loc: VacancyDetails['location']): string | null {
  if (!loc) return null
  const parts: string[] = []
  if (loc.remote === true) parts.push('Remote')
  if (loc.remote === false) parts.push('Office')
  if (loc.cities.length > 0) parts.push(loc.cities.join(', '))
  return parts.length > 0 ? parts.join(' · ') : null
}

function skillsText(ids: string[]): string {
  return ids.map(skillName).join(' / ')
}

function years(n: number): string {
  return `${Number.isInteger(n) ? n : n.toFixed(1)} ${n === 1 ? 'year' : 'years'}`
}

export function SkillChips({ checks }: { checks: RequirementCheck[] }) {
  const required = checks.flatMap((c) => (c.kind === 'skill' && c.required ? [c] : []))
  if (required.length === 0) return null
  return (
    <ul className="chips" aria-label="Required skills">
      {required.map((c) => (
        <li
          key={c.skills.join('|')}
          className={`chip chip-${c.status}`}
          data-status={c.status}
          title={`needs: ${levelName(c.minLevel)}; profile: ${levelName(c.level)}`}
        >
          <span className="chip-mark" aria-hidden="true" />
          {skillsText(c.skills)}
          <span className="sr-only">: {STATUS_TEXT[c.status]}</span>
        </li>
      ))}
    </ul>
  )
}

export function ChipLegend() {
  return (
    <ul className="legend" aria-label="Chip legend">
      {(Object.keys(STATUS_TEXT) as CheckStatus[]).map((s) => (
        <li key={s} className={`legend-item chip-${s}`}>
          <span className="chip-mark" aria-hidden="true" />
          {STATUS_TEXT[s]}
        </li>
      ))}
    </ul>
  )
}

function CheckLine({ c }: { c: RequirementCheck }) {
  let what: string
  let have: string
  let quote: string | null
  let tag: string | null = null
  switch (c.kind) {
    case 'skill':
      what = skillsText(c.skills)
      have = `needs ${shortLevelName(c.minLevel)}, profile: ${shortLevelName(c.level)}`
      quote = c.evidence
      tag = c.required ? 'required' : 'nice to have'
      break
    case 'experience':
      what = 'Experience'
      have = `needs ${c.maxYears === null ? `${c.minYears}+` : `${c.minYears}–${c.maxYears}`} years, profile: ${years(c.years)}`
      quote = null
      break
    case 'english':
      what = 'English'
      have = `needs ${c.minLevel}, profile: ${c.english ?? 'not stated'}`
      quote = c.evidence
      break
  }
  return (
    <li className={`check check-${c.status}`} data-status={c.status}>
      <span className="check-mark" aria-hidden="true" />
      <div className="check-body">
        <p className="check-head">
          <strong>{what}</strong>
          <span className="sr-only">: {STATUS_TEXT[c.status]}</span>
          {tag && <span className="check-tag">{tag}</span>}
        </p>
        <p className="check-have">{have}</p>
        {quote && <q className="check-quote">{quote}</q>}
      </div>
    </li>
  )
}

// What the profile lacks for this vacancy, shown before the chips: required skills short on years or absent,
// then experience and English when below the bar.
function MissingLine({ checks }: { checks: RequirementCheck[] }) {
  const gaps = checks.flatMap((c) => {
    if (c.status === 'covered') return []
    if (c.kind === 'skill') {
      if (!c.required) return []
      const have = c.level > 0 ? `, you ${levelName(c.level)}` : ''
      return [`${skillsText(c.skills)} (needs ${levelName(c.minLevel)}${have})`]
    }
    if (c.kind === 'experience') return [`experience (needs ${c.minYears}+ years, you ${years(c.years)})`]
    return [`English (needs ${c.minLevel}, you ${c.english ?? 'not stated'})`]
  })
  if (gaps.length === 0) return null
  return (
    <p className="vacancy-missing">
      <strong>Missing:</strong> {gaps.join(' · ')}
    </p>
  )
}

export function VacancyCard({ row, details, showDelta }: { row: VacancyRow; details?: VacancyDetails; showDelta: boolean }) {
  const loc = locationText(details?.location ?? null)
  const checks = details?.checks ?? []
  return (
    <li className="card vacancy">
      <div className="vacancy-top">
        <CoverageRing coverage={row.coverage} fits={row.fits} />
        <div className="vacancy-main">
          <h3 className="vacancy-title">
            {row.url ? (
              <a href={row.url} target="_blank" rel="noreferrer">
                {row.title}
              </a>
            ) : (
              row.title
            )}
          </h3>
          <p className="vacancy-meta">
            {row.company && <span className="company">{row.company}</span>}
            {loc && (
              <span className="location">
                {row.company ? ' · ' : ''}
                {loc}
              </span>
            )}
          </p>
        </div>
        <div className="vacancy-score">
          {row.fits && <span className="badge-fits">fits</span>}
          {showDelta && row.coverage !== null && row.openingCoverage !== null && (
            <span className="vacancy-delta">
              <Delta value={(row.coverage - row.openingCoverage) * 100} unit="pp vs opening" />
            </span>
          )}
        </div>
      </div>
      <MissingLine checks={checks} />
      <SkillChips checks={checks} />
      {checks.length > 0 && (
        <details className="reqs">
          <summary>All requirements ({checks.length})</summary>
          <ul className="checks">
            {checks.map((c, i) => (
              <CheckLine key={i} c={c} />
            ))}
          </ul>
        </details>
      )}
    </li>
  )
}

export function VacancyList({
  rows,
  details = {},
  showDelta,
}: {
  rows: VacancyRow[]
  details?: Record<string, VacancyDetails>
  showDelta: boolean
}) {
  return (
    <section className="vacancies-section" aria-labelledby="vacancies-h">
      <div className="section-head">
        <h2 id="vacancies-h" className="section-h">
          Vacancies <span className="count num">{rows.length}</span>
        </h2>
        <ChipLegend />
      </div>
      <ul className="vacancies">
        {sortVacancyRows(rows).map((r) => (
          <VacancyCard key={r.id} row={r} details={details[r.id]} showDelta={showDelta} />
        ))}
      </ul>
    </section>
  )
}
