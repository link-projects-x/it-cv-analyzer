// Hints: the effect of moving one visible slider one step up from the current state.
// Plain code over the same selectors the page shows; no LLM.
import { COVERAGE_CONFIG, shortLevelName, skillName } from './contracts'
import {
  coverages,
  dragSkill,
  english,
  experienceYears,
  meanCoverage,
  salaryEstimate,
  setEnglish,
  setExperience,
  skillLevel,
  type SalaryEstimate,
  type State,
} from './state'
import type { Cefr, CoverageVacancy, Salary } from './types'

export interface Hint {
  key: string
  label: string
  from: string
  to: string
  fitsDelta: number
  // change of the mean coverage, in percentage points
  coverageDeltaPp: number
  // null when the salary estimate cannot change for this step (skill sliders, or the grid
  // rules give a dash before or after the step)
  salaryDelta: number | null
  text: string
}

const EPS = 1e-9

function salaryValue(est: SalaryEstimate): number | null {
  return est.kind === 'none' ? null : est.value
}

// "+4.1", "-2", "0": a value that rounds to zero is printed without a sign.
export function signed(n: number, digits = 0): string {
  const rounded = n.toFixed(digits)
  if (Number(rounded) === 0) return (0).toFixed(digits)
  return n > 0 ? `+${rounded}` : rounded
}

export function hintText(h: Omit<Hint, 'text' | 'key'>): string {
  const vacancies = `${signed(h.fitsDelta)} ${Math.abs(h.fitsDelta) === 1 ? 'vacancy' : 'vacancies'}`
  const parts = [vacancies, `${signed(h.coverageDeltaPp, 1)} pp`]
  if (h.salaryDelta !== null) parts.push(`${signed(h.salaryDelta)} USD/month`)
  return `${h.label}: ${h.from} → ${h.to}: ${parts.join(', ')}`
}

interface Step {
  key: string
  label: string
  from: string
  to: string
  next: State
}

function steps(state: State, skillIds: string[]): Step[] {
  const out: Step[] = []
  const { skill, experience_years: exp, english: eng } = COVERAGE_CONFIG.sliders

  // One hint step is one more year with a skill: a half-year slider step moves coverage too little to rank by.
  const hintYears = Math.max(1, skill.step)
  for (const id of skillIds) {
    const level = skillLevel(state, id)
    if (level + hintYears > skill.max) continue
    out.push({
      key: `skill:${id}`,
      label: skillName(id),
      from: shortLevelName(level),
      to: shortLevelName(level + hintYears),
      next: dragSkill(state, id, level + hintYears),
    })
  }

  const years = experienceYears(state)
  const nextYears = exp.min + (Math.floor((years - exp.min) / exp.step) + 1) * exp.step
  if (nextYears <= exp.max) {
    out.push({
      key: 'experience',
      label: 'Experience',
      from: `${years}`,
      to: `${nextYears} years`,
      next: setExperience(state, nextYears),
    })
  }

  const level = english(state)
  const nextLevel = eng.values[level === null ? 0 : eng.values.indexOf(level) + 1]
  if (nextLevel !== undefined) {
    out.push({
      key: 'english',
      label: 'English',
      from: level ?? 'not stated',
      to: nextLevel,
      next: setEnglish(state, nextLevel as Cefr),
    })
  }
  return out
}

function compare(a: Hint, b: Hint): number {
  if (a.fitsDelta !== b.fitsDelta) return b.fitsDelta - a.fitsDelta
  if (Math.abs(a.coverageDeltaPp - b.coverageDeltaPp) > EPS) return b.coverageDeltaPp - a.coverageDeltaPp
  return (b.salaryDelta ?? 0) - (a.salaryDelta ?? 0)
}

// All one-step hints with a non-zero effect, ranked by fits change, then mean coverage change,
// then salary change (null counts as 0). Ties keep the slider order given in `skillIds`, then
// experience, then English.
export function rankedHints(
  state: State,
  vacancies: CoverageVacancy[],
  salary: Salary,
  skillIds: string[],
): Hint[] {
  const before = coverages(state, vacancies)
  const fitsBefore = before.filter((c) => c.fits).length
  const meanBefore = meanCoverage(before)
  const salaryBefore = salaryValue(salaryEstimate(state, salary))

  const out: Hint[] = []
  for (const step of steps(state, skillIds)) {
    const after = coverages(step.next, vacancies)
    const fitsDelta = after.filter((c) => c.fits).length - fitsBefore
    const coverageDeltaPp = (meanCoverage(after) - meanBefore) * 100
    const isSalaryInput = step.key === 'experience' || step.key === 'english'
    const salaryAfter = salaryValue(salaryEstimate(step.next, salary))
    const salaryDelta =
      isSalaryInput && salaryBefore !== null && salaryAfter !== null ? salaryAfter - salaryBefore : null

    if (fitsDelta === 0 && Math.abs(coverageDeltaPp) <= EPS && (salaryDelta ?? 0) === 0) continue

    const base = { label: step.label, from: step.from, to: step.to, fitsDelta, coverageDeltaPp, salaryDelta }
    out.push({ ...base, key: step.key, text: hintText(base) })
  }
  return out.sort(compare)
}

// Top 5 hints for the visible skill sliders plus the experience and English sliders.
export function hints(
  state: State,
  vacancies: CoverageVacancy[],
  salary: Salary,
  skillIds: string[],
  limit = 5,
): Hint[] {
  return rankedHints(state, vacancies, salary, skillIds).slice(0, limit)
}
