// Slider state: the opening values from the API response plus the values the user moved (`touched`).
// Every function here is pure; React only stores the State object.
import { COVERAGE_CONFIG } from './contracts'
import { coverage, type CoverageResult } from './coverage'
import type { Cefr, CoverageProfile, CoverageVacancy, MatchResponse, Salary } from './types'

export interface Opening {
  skills: Record<string, number>
  // evidence per profile skill; null when the CV parser gave a level without a quote
  evidence: Record<string, string | null>
  experienceYears: number
  english: Cefr | null
}

export interface Touched {
  skills: Record<string, number>
  // a key is present only while the value differs from the opening one
  experienceYears?: number
  english?: Cefr | null
}

export interface State {
  opening: Opening
  touched: Touched
}

const SLIDERS = COVERAGE_CONFIG.sliders

export function initialState(response: Pick<MatchResponse, 'profile'>): State {
  const skills: Record<string, number> = {}
  const evidence: Record<string, string | null> = {}
  for (const s of response.profile.skills) {
    skills[s.id] = Math.max(skills[s.id] ?? 0, s.level)
    evidence[s.id] = evidence[s.id] ?? s.evidence
  }
  return {
    opening: {
      skills,
      evidence,
      experienceYears: response.profile.experience_years,
      english: response.profile.english,
    },
    touched: { skills: {} },
  }
}

function clampToStep(value: number, range: { min: number; max: number; step: number }): number {
  const stepped = range.min + Math.round((value - range.min) / range.step) * range.step
  return Math.min(range.max, Math.max(range.min, stepped))
}

function without<T extends object>(obj: T, key: keyof T): T {
  const copy = { ...obj }
  Reflect.deleteProperty(copy, key)
  return copy
}

export function openingSkillLevel(state: State, id: string): number {
  return state.opening.skills[id] ?? 0
}

export function skillLevel(state: State, id: string): number {
  return state.touched.skills[id] ?? openingSkillLevel(state, id)
}

// Slider position and salary grid key for an experience value (contracts/README.md -> Salary grid):
// the nearest whole year, half rounds up, clamped to the slider range (0-15).
export function experiencePosition(years: number): number {
  const { min, max } = SLIDERS.experience_years
  return Math.min(max, Math.max(min, Math.floor(years + 0.5)))
}

// The position the experience slider opens at.
export function openingExperiencePosition(state: State): number {
  return experiencePosition(state.opening.experienceYears)
}

// The experience slider position: the moved value, else the opening position.
export function experienceYears(state: State): number {
  return state.touched.experienceYears ?? openingExperiencePosition(state)
}

export function english(state: State): Cefr | null {
  return 'english' in state.touched ? (state.touched.english ?? null) : state.opening.english
}

export function dragSkill(state: State, id: string, level: number): State {
  const value = clampToStep(level, SLIDERS.skill)
  const rest = without(state.touched.skills, id)
  const skills = value === openingSkillLevel(state, id) ? rest : { ...rest, [id]: value }
  return { ...state, touched: { ...state.touched, skills } }
}

export function setExperience(state: State, years: number): State {
  const rest = without(state.touched, 'experienceYears')
  const value = clampToStep(years, SLIDERS.experience_years)
  if (value === openingExperiencePosition(state)) return { ...state, touched: rest }
  return { ...state, touched: { ...rest, experienceYears: value } }
}

export function setEnglish(state: State, cefr: Cefr | null): State {
  const rest = without(state.touched, 'english')
  if (cefr === state.opening.english) return { ...state, touched: rest }
  return { ...state, touched: { ...rest, english: cefr } }
}

export function reset(state: State): State {
  return { ...state, touched: { skills: {} } }
}

// --- selectors ---------------------------------------------------------------

export function currentProfile(state: State): CoverageProfile {
  return {
    skills: { ...state.opening.skills, ...state.touched.skills },
    // Until the slider moves, coverage reads the profile value as parsed (3.5 stays 3.5).
    experience_years: state.touched.experienceYears ?? state.opening.experienceYears,
    english: english(state),
  }
}

export function openingProfile(state: State): CoverageProfile {
  return currentProfile(reset(state))
}

export function isTouched(state: State): boolean {
  return (
    Object.keys(state.touched.skills).length > 0 ||
    'experienceYears' in state.touched ||
    'english' in state.touched
  )
}

export function coverages(state: State, vacancies: CoverageVacancy[]): CoverageResult[] {
  const profile = currentProfile(state)
  return vacancies.map((v) => coverage(profile, v))
}

export function fitsCount(state: State, vacancies: CoverageVacancy[]): number {
  return coverages(state, vacancies).filter((c) => c.fits).length
}

// Mean over the vacancies that have something to score (coverage not null); 0 when none do.
export function meanCoverage(results: CoverageResult[]): number {
  const values = results.flatMap((r) => (r.coverage === null ? [] : [r.coverage]))
  return values.length === 0 ? 0 : values.reduce((a, b) => a + b, 0) / values.length
}

// The level the CV supports: the opening level when the profile skill has a quote, else 0.
export function cvSupportedLevel(state: State, id: string): number {
  return state.opening.evidence[id] ? openingSkillLevel(state, id) : 0
}

// Tick on the track: only for profile skills whose evidence is not null.
export function cvTick(state: State, id: string): number | null {
  return state.opening.evidence[id] ? openingSkillLevel(state, id) : null
}

// --- salary ------------------------------------------------------------------

export type SalaryEstimate =
  | { kind: 'point'; value: number; low: number | null; high: number | null }
  | { kind: 'grid'; value: number; input: 'english' | 'experience_years' }
  | { kind: 'none'; reason: 'two-settings' | 'missing-grid-key' }

// salary.grid varies one input at a time with the rest of the profile unchanged, so the page
// reads the grid only while exactly one salary input differs from its opening value.
// Skill levels are not salary inputs.
export function salaryEstimate(state: State, salary: Salary): SalaryEstimate {
  const englishMoved = 'english' in state.touched
  const experienceMoved = 'experienceYears' in state.touched

  if (englishMoved && experienceMoved) return { kind: 'none', reason: 'two-settings' }

  if (englishMoved) {
    const level = english(state)
    const value = level === null ? undefined : salary.grid.english[level]
    return value === undefined
      ? { kind: 'none', reason: 'missing-grid-key' }
      : { kind: 'grid', value, input: 'english' }
  }

  if (experienceMoved) {
    const value = salary.grid.experience_years[String(experienceYears(state))]
    return value === undefined
      ? { kind: 'none', reason: 'missing-grid-key' }
      : { kind: 'grid', value, input: 'experience_years' }
  }

  return { kind: 'point', value: salary.point, low: salary.low, high: salary.high }
}
