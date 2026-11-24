// Headline plan: up to three "+1 year with a skill" steps, each the best next hint (most new fits, then mean
// coverage), applied one after another. Plain greedy search over the hint ranking; no LLM.
import { skillName } from './contracts'
import { rankedHints } from './hints'
import { coverages, dragSkill, skillLevel, type State } from './state'
import type { CoverageVacancy, Salary } from './types'

export interface PlanStep {
  id: string
  name: string
  from: number
  to: number
}

export interface Plan {
  steps: PlanStep[]
  fitsBefore: number
  fitsAfter: number
}

export function improvementPlan(
  state: State,
  vacancies: CoverageVacancy[],
  salary: Salary,
  skillIds: string[],
  maxSteps = 3,
): Plan {
  const fits = (s: State) => coverages(s, vacancies).filter((c) => c.fits).length
  const fitsBefore = fits(state)
  let current = state
  const steps: PlanStep[] = []
  for (let i = 0; i < maxSteps; i++) {
    const best = rankedHints(current, vacancies, salary, skillIds).find((h) => h.key.startsWith('skill:'))
    if (!best || (best.fitsDelta <= 0 && best.coverageDeltaPp <= 0)) break
    const id = best.key.slice('skill:'.length)
    const from = skillLevel(current, id)
    const to = from + 1
    current = dragSkill(current, id, to)
    const same = steps.find((s) => s.id === id)
    if (same) same.to = to
    else steps.push({ id, name: skillName(id), from, to })
  }
  return { steps, fitsBefore, fitsAfter: fits(current) }
}
