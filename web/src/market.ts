// "Market vs you": the skills the vacancies require most, how many years they typically ask, and the profile's
// years. One row per requirement option set ("AWS / Azure / GCP" is one row), counted once per vacancy.
import { skillName } from './contracts'
import { effectiveLevels, neededYears } from './coverage'
import type { CoverageVacancy } from './types'

export type MarketStatus = 'covered' | 'partial' | 'missing'

export interface MarketRow {
  key: string
  label: string
  skills: string[]
  /** share of the vacancies that list the row as required, 0..1 */
  share: number
  vacancies: number
  /** median of the years the vacancies ask for it */
  medianYears: number
  /** the profile's best years among the row's skills */
  years: number
  status: MarketStatus
}

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  const at = (i: number) => s[i] ?? 0
  return s.length % 2 ? at(mid) : (at(mid - 1) + at(mid)) / 2
}

const ORDER: Record<MarketStatus, number> = { missing: 0, partial: 1, covered: 2 }

/** Rows for the required skills, gaps first (missing, then short on years), each group by share; at most `limit`. */
export function marketRows(vacancies: CoverageVacancy[], profileSkills: Record<string, number>, limit = 15): MarketRow[] {
  const levels = effectiveLevels(profileSkills)
  const by = new Map<string, { skills: string[]; needs: number[] }>()
  for (const v of vacancies) {
    const seen = new Set<string>()
    for (const r of v.requirements) {
      if (!r.required) continue
      const key = [...r.any_of].sort().join('|')
      if (seen.has(key)) continue
      seen.add(key)
      const entry = by.get(key) ?? { skills: [...r.any_of].sort(), needs: [] }
      entry.needs.push(neededYears(r, v))
      by.set(key, entry)
    }
  }
  const total = vacancies.length || 1
  const rows: MarketRow[] = [...by.entries()].map(([key, { skills, needs }]) => {
    const years = Math.max(...skills.map((id) => levels[id] ?? 0))
    const medianYears = median(needs)
    const status: MarketStatus = years <= 0 ? 'missing' : years >= medianYears ? 'covered' : 'partial'
    return {
      key,
      label: skills.map(skillName).join(' / '),
      skills,
      share: needs.length / total,
      vacancies: needs.length,
      medianYears,
      years,
      status,
    }
  })
  // The top rows by share first, so a rare skill does not push out a common one; then gaps first inside them.
  return rows
    .sort((a, b) => b.share - a.share)
    .slice(0, limit)
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.share - a.share)
}
