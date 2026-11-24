// Which skill sliders the page draws: a skill gets a slider only if moving it from the slider
// minimum (0) to the maximum (3) changes the coverage of at least one loaded vacancy.
// The hierarchy is part of coverage(), so a child skill (aws-bedrock) is shown for a vacancy
// that requires its parent (aws).
import { COVERAGE_CONFIG, SKILLS } from './contracts'
import { coverage } from './coverage'
import type { CoverageProfile, CoverageVacancy, SkillDef } from './types'

export interface SkillSlider {
  id: string
  name: string
  // vacancies whose coverage changes between level 0 and level 3
  vacancies: number
  // vacancies that list the skill in a requirement's any_of
  direct: number
}

function sameCoverage(a: number | null, b: number | null): boolean {
  if (a === null || b === null) return a === b
  return Math.abs(a - b) <= 1e-12
}

// `profile` holds the other skill levels while one skill is tested; the page passes the opening
// profile so the set of sliders does not change while the user drags.
export function visibleSkillSliders(
  profile: CoverageProfile,
  vacancies: CoverageVacancy[],
  catalog: SkillDef[] = SKILLS,
): SkillSlider[] {
  const { min, max } = COVERAGE_CONFIG.sliders.skill
  const out: SkillSlider[] = []
  for (const skill of catalog) {
    const low = { ...profile, skills: { ...profile.skills, [skill.id]: min } }
    const high = { ...profile, skills: { ...profile.skills, [skill.id]: max } }
    let moved = 0
    let direct = 0
    for (const v of vacancies) {
      const before = coverage(low, v, COVERAGE_CONFIG, catalog).coverage
      const after = coverage(high, v, COVERAGE_CONFIG, catalog).coverage
      if (!sameCoverage(before, after)) moved += 1
      if (v.requirements.some((r) => r.any_of.includes(skill.id))) direct += 1
    }
    if (moved > 0) out.push({ id: skill.id, name: skill.name, vacancies: moved, direct })
  }
  // Skills that move the most vacancies first; ties: listed directly by more vacancies, then name.
  return out.sort(
    (a, b) => b.vacancies - a.vacancies || b.direct - a.direct || a.name.localeCompare(b.name, 'en'),
  )
}
