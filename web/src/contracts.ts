// Contract files imported through the @contracts alias (vite.config.ts), not copied.
import coverageJson from '@contracts/coverage.json'
import skillsJson from '@contracts/skills.json'
import type { CoverageConfig, SkillDef, SkillsDoc } from './types'

export const COVERAGE_CONFIG: CoverageConfig = coverageJson
export const SKILLS_DOC: SkillsDoc = skillsJson
export const SKILLS: SkillDef[] = skillsJson.skills

const skillById = new Map(SKILLS.map((s) => [s.id, s]))

export function skillName(id: string): string {
  return skillById.get(id)?.name ?? id
}

// Skill sliders hold years with the skill (coverage formula v2); 0 reads "none".
export function levelName(years: number): string {
  if (years <= 0) return 'none'
  const n = Number.isInteger(years) ? String(years) : years.toFixed(1)
  return `${n} ${years === 1 ? 'year' : 'years'}`
}

export function shortLevelName(years: number): string {
  return levelName(years)
}
