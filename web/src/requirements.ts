// Per-requirement check for the vacancy card: how much of each requirement the current profile covers.
// Scores follow contracts/README.md -> Coverage formula, one part at a time; coverage.ts stays the
// source of the total.
import { COVERAGE_CONFIG, SKILLS } from './contracts'
import { effectiveLevels, neededYears, skillScore } from './coverage'
import type { Cefr, CoverageProfile, CoverageVacancy, SkillDef } from './types'

export type CheckStatus = 'covered' | 'partial' | 'missing'

export type RequirementCheck =
  | {
      kind: 'skill'
      skills: string[]
      // years the requirement asks for (its own, or inherited from the vacancy: coverage.ts neededYears)
      minLevel: number
      required: boolean
      evidence: string
      // the best effective level among any_of
      level: number
      score: number
      status: CheckStatus
    }
  | { kind: 'experience'; minYears: number; maxYears: number | null; years: number; score: number; status: CheckStatus }
  | { kind: 'english'; minLevel: Cefr; english: Cefr | null; evidence: string | null; score: number; status: CheckStatus }

const EPS = 1e-12

export function checkStatus(score: number): CheckStatus {
  if (score >= 1 - EPS) return 'covered'
  return score > 0 ? 'partial' : 'missing'
}

export function requirementChecks(
  profile: CoverageProfile,
  vacancy: CoverageVacancy,
  catalog: SkillDef[] = SKILLS,
): RequirementCheck[] {
  const levels = effectiveLevels(profile.skills, catalog)
  const out: RequirementCheck[] = vacancy.requirements.map((r) => {
    const level = Math.max(...r.any_of.map((id) => levels[id] ?? 0))
    const need = neededYears(r, vacancy)
    const score = skillScore(level, need)
    return {
      kind: 'skill',
      skills: r.any_of,
      minLevel: need,
      required: r.required,
      evidence: r.evidence,
      level,
      score,
      status: checkStatus(score),
    }
  })

  const minYears = vacancy.experience.min_years
  if (minYears) {
    const score = Math.min(1, profile.experience_years / minYears)
    out.push({
      kind: 'experience',
      minYears,
      maxYears: vacancy.experience.max_years,
      years: profile.experience_years,
      score,
      status: checkStatus(score),
    })
  }

  const need = vacancy.english.min_level
  if (need !== null) {
    const order = COVERAGE_CONFIG.cefr_order
    const haveI = profile.english ? order.indexOf(profile.english) + 1 : 0
    const needI = order.indexOf(need) + 1
    const score = haveI >= needI ? 1 : haveI / needI
    out.push({
      kind: 'english',
      minLevel: need,
      english: profile.english,
      evidence: vacancy.english.evidence,
      score,
      status: checkStatus(score),
    })
  }
  return out
}
