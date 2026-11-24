// Coverage formula v1: contracts/README.md -> Coverage formula.
// Mirrors contracts/coverage_reference.py step by step; parity is checked against
// contracts/fixtures/coverage-golden.json in coverage.test.ts.
import { COVERAGE_CONFIG, SKILLS } from './contracts'
import type { CoverageConfig, CoverageProfile, CoverageVacancy, SkillDef } from './types'

export interface CoverageResult {
  coverage: number | null
  fits: boolean
}

// Profile levels after the hierarchy rule: a parent's level is the max of its own level
// and its descendants' levels. The hierarchy does not flow down to children.
export function effectiveLevels(
  profileSkills: Record<string, number>,
  catalog: SkillDef[] = SKILLS,
): Record<string, number> {
  const parentOf = new Map<string, string | undefined>(catalog.map((s) => [s.id, s.parent]))
  const levels: Record<string, number> = { ...profileSkills }
  for (const [id, level] of Object.entries(profileSkills)) {
    let parent = parentOf.get(id)
    const seen = new Set<string>() // guards against a cycle in skills.json
    while (parent !== undefined && !seen.has(parent)) {
      seen.add(parent)
      levels[parent] = Math.max(levels[parent] ?? 0, level)
      parent = parentOf.get(parent)
    }
  }
  return levels
}

/** Years a requirement asks for: its own min_years, else the vacancy's experience (or the grade's typical
 * years, or default_years) times inherit_factor. Mirrors needed_years() in coverage_reference.py. */
export function neededYears(
  req: { min_years?: number | null },
  vacancy: Pick<CoverageVacancy, 'experience' | 'seniority'>,
  cfg: CoverageConfig = COVERAGE_CONFIG,
): number {
  if (req.min_years !== undefined && req.min_years !== null) return req.min_years
  const sy = cfg.skill_years
  const base = vacancy.experience.min_years || sy.grade_years[vacancy.seniority ?? 'unknown'] || sy.default_years
  return base * sy.inherit_factor
}

/** 0 without the skill; otherwise the share of the needed years, capped at 1. */
export function skillScore(years: number, need: number): number {
  if (years <= 0) return 0
  return need <= 0 ? 1 : Math.min(1, years / need)
}

export function coverage(
  profile: CoverageProfile,
  vacancy: CoverageVacancy,
  cfg: CoverageConfig = COVERAGE_CONFIG,
  catalog: SkillDef[] = SKILLS,
): CoverageResult {
  const w = cfg.weights
  const levels = effectiveLevels(profile.skills, catalog)

  let skillsPart = 0
  let skillsMax = 0
  for (const req of vacancy.requirements) {
    const weight = req.required ? w.required : w.optional
    const need = neededYears(req, vacancy, cfg)
    const score = Math.max(...req.any_of.map((id) => skillScore(levels[id] ?? 0, need)))
    skillsPart += weight * score
    skillsMax += weight
  }

  let expPart = 0
  let expMax = 0
  const minYears = vacancy.experience.min_years
  if (minYears) {
    // null or 0: the vacancy asks for no experience, so the part is skipped
    expPart = w.experience * Math.min(1, profile.experience_years / minYears)
    expMax = w.experience
  }

  let engPart = 0
  let engMax = 0
  const need = vacancy.english.min_level
  if (need !== null) {
    const order = cfg.cefr_order
    const have = profile.english
    const haveI = have ? order.indexOf(have) + 1 : 0
    const needI = order.indexOf(need) + 1
    engPart = w.english * (haveI >= needI ? 1 : haveI / needI)
    engMax = w.english
  }

  const totalMax = skillsMax + expMax + engMax
  if (totalMax === 0) return { coverage: null, fits: false }

  const value = (skillsPart + expPart + engPart) / totalMax
  // Same tolerance as coverage_reference.py: 0.8 computed as a sum of floats still fits.
  return { coverage: value, fits: value >= cfg.fits_threshold - 1e-12 }
}
