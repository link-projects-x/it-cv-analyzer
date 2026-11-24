// Types for the parts of contracts/*.schema.json the page reads.
// Fields the page does not read are left out; JSON documents may carry more.

export type Cefr = 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2'

export interface Requirement {
  any_of: string[]
  min_level: number
  /** years asked for this skill; absent in files parsed before 2026-11-22 */
  min_years?: number | null
  required: boolean
  evidence: string
}

export interface Vacancy {
  id: string
  url: string
  title: string
  company: string
  requirements: Requirement[]
  seniority?: string
  experience: { min_years: number | null; max_years: number | null }
  english: { min_level: Cefr | null; evidence: string | null }
  location: { remote: boolean | null; cities: string[] }
}

export interface ProfileSkill {
  id: string
  level: number
  evidence: string | null
}

export interface Profile {
  skills: ProfileSkill[]
  experience_years: number
  english: Cefr | null
}

export interface Salary {
  currency: 'USD'
  period: 'month'
  point: number
  low: number | null
  high: number | null
  model_version: string
  grid: {
    english: Partial<Record<Cefr, number>>
    experience_years: Record<string, number>
    company_type: Record<string, number>
    domains: Record<string, number>
  }
}

export interface MatchResponse {
  schema_version: string
  profile: Profile
  vacancies: { similarity: number; vacancy: Vacancy }[]
  salary: Salary
  // Static mode only (src/local): the DOU category the vacancies come from, the categories the person can
  // switch to, and a function that matches the same CV against another category.
  category?: string
  categories?: { name: string; count: number }[]
  rematch?: (category: string) => MatchResponse
  /** skill IDs the CV lists without dated job entries; their years are the CV's total experience */
  undated?: string[]
  /** the grade vacancies were filtered by (CV grade ±1) */
  grade?: string
  /** every vacancy of the category after the filters, for the "what these vacancies require" table */
  marketVacancies?: Vacancy[]
}

// contracts/coverage.json
export interface CoverageConfig {
  weights: { required: number; optional: number; experience: number; english: number }
  fits_threshold: number
  cefr_order: string[]
  skill_years: { grade_years: Record<string, number>; default_years: number; inherit_factor: number }
  sliders: {
    skill: { min: number; max: number; step: number }
    experience_years: { min: number; max: number; step: number }
    english: { values: string[] }
  }
}

// contracts/skills.json
export interface SkillDef {
  id: string
  name: string
  group: string
  parent?: string
  aliases: string[]
}

export interface SkillsDoc {
  levels: Record<string, string>
  skills: SkillDef[]
}

// The profile shape the coverage formula reads (same as the golden file's "profile").
export interface CoverageProfile {
  /** skill ID -> years */
  skills: Record<string, number>
  experience_years: number
  english: Cefr | null
}

// The vacancy fields the coverage formula reads.
export type CoverageVacancy = Pick<Vacancy, 'requirements' | 'experience' | 'english' | 'seniority'>
