// Small builders for tests.
import type { Cefr, CoverageVacancy, MatchResponse, Requirement, Salary } from './types'

// minYears: years the requirement asks for this skill (coverage formula v2); min_level is kept for the schema.
export function req(anyOf: string[], minYears: number, required = true): Requirement {
  return { any_of: anyOf, min_level: Math.min(3, Math.max(1, Math.round(minYears))), min_years: minYears, required, evidence: 'x' }
}

export function vac(requirements: Requirement[], minYears: number | null = null, english: Cefr | null = null): CoverageVacancy {
  return {
    requirements,
    experience: { min_years: minYears, max_years: null },
    english: { min_level: english, evidence: english ? 'x' : null },
  }
}

export function profileResponse(
  skills: { id: string; level: number; evidence?: string | null }[],
  experienceYears = 2,
  english: Cefr | null = 'B2',
): Pick<MatchResponse, 'profile'> {
  return {
    profile: {
      skills: skills.map((s) => ({ id: s.id, level: s.level, evidence: s.evidence === undefined ? 'quote' : s.evidence })),
      experience_years: experienceYears,
      english,
    },
  }
}

export function salary(overrides: Partial<Salary> = {}): Salary {
  return {
    currency: 'USD',
    period: 'month',
    point: 2700,
    low: null,
    high: null,
    model_version: 'test',
    grid: {
      english: { B1: 2300, B2: 2700, C1: 3100 },
      // consistent with the point: grid at the opening position (B2, 2 years) equals point
      experience_years: { '1': 2370, '2': 2700, '3': 3030 },
      company_type: {},
      domains: {},
    },
    ...overrides,
  }
}
