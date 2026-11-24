// Numbers for the stat cards: current values and their change against the opening state.
import { coverages, meanCoverage, reset, salaryEstimate, type SalaryEstimate, type State } from './state'
import type { CoverageVacancy, Salary } from './types'

export interface Summary {
  fits: number
  total: number
  // mean over vacancies with coverage not null, 0..1
  mean: number
  salary: SalaryEstimate
}

export interface SummaryDelta {
  fits: number
  // percentage points
  meanPp: number
  // USD per month; null when the current or the opening estimate is a dash
  salary: number | null
}

export function summary(state: State, vacancies: CoverageVacancy[], salary: Salary): Summary {
  const results = coverages(state, vacancies)
  return {
    fits: results.filter((r) => r.fits).length,
    total: vacancies.length,
    mean: meanCoverage(results),
    salary: salaryEstimate(state, salary),
  }
}

export function openingSummary(state: State, vacancies: CoverageVacancy[], salary: Salary): Summary {
  return summary(reset(state), vacancies, salary)
}

function salaryValue(e: SalaryEstimate): number | null {
  return e.kind === 'none' ? null : e.value
}

export function summaryDelta(current: Summary, opening: Summary): SummaryDelta {
  const now = salaryValue(current.salary)
  const was = salaryValue(opening.salary)
  return {
    fits: current.fits - opening.fits,
    meanPp: (current.mean - opening.mean) * 100,
    salary: now === null || was === null ? null : now - was,
  }
}
