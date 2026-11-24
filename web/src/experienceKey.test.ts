// Experience slider position and salary grid key: contracts/README.md -> Salary grid.
import { describe, expect, it } from 'vitest'
import { hints } from './hints'
import {
  currentProfile,
  experiencePosition,
  experienceYears,
  initialState,
  isTouched,
  openingExperiencePosition,
  salaryEstimate,
  setExperience,
} from './state'
import { profileResponse, salary } from './testData'

const grid = salary({
  grid: {
    english: { B2: 2700 },
    experience_years: Object.fromEntries(Array.from({ length: 16 }, (_, i) => [String(i), 1000 + 100 * i])),
    company_type: {},
    domains: {},
  },
})

const at = (years: number) => initialState(profileResponse([], years, 'B2'))

describe('experiencePosition', () => {
  it('rounds to the nearest whole year, half up, and clamps to 0-15', () => {
    expect(experiencePosition(3.4)).toBe(3)
    expect(experiencePosition(3.5)).toBe(4)
    expect(experiencePosition(2.5)).toBe(3)
    expect(experiencePosition(0.49)).toBe(0)
    expect(experiencePosition(20)).toBe(15)
    expect(experiencePosition(-1)).toBe(0)
  })
})

describe('non-integer and out-of-range opening experience', () => {
  it('the slider opens at the rounded position; coverage keeps the parsed value', () => {
    const s = at(3.5)
    expect(openingExperiencePosition(s)).toBe(4)
    expect(experienceYears(s)).toBe(4)
    expect(currentProfile(s).experience_years).toBe(3.5)
  })

  it('moving to the opening position is not a move: the point estimate stays', () => {
    const s = setExperience(at(3.5), 4)
    expect(isTouched(s)).toBe(false)
    expect(salaryEstimate(s, grid)).toEqual({ kind: 'point', value: 2700, low: null, high: null })
  })

  it('a moved position reads the grid with the integer key, never a dash', () => {
    expect(salaryEstimate(setExperience(at(3.5), 5), grid)).toEqual({
      kind: 'grid',
      value: 1500,
      input: 'experience_years',
    })
    expect(salaryEstimate(setExperience(at(3.4), 4), grid)).toEqual({
      kind: 'grid',
      value: 1400,
      input: 'experience_years',
    })
    expect(currentProfile(setExperience(at(3.5), 5)).experience_years).toBe(5)
  })

  it('experience above the range opens at 15; 15 is the opening position', () => {
    const s = at(20)
    expect(experienceYears(s)).toBe(15)
    expect(isTouched(setExperience(s, 15))).toBe(false)
    expect(salaryEstimate(setExperience(s, 14), grid)).toEqual({ kind: 'grid', value: 2400, input: 'experience_years' })
  })

  it('the experience hint steps from the opening position', () => {
    const h = hints(at(3.5), [], grid, []).find((x) => x.key === 'experience')
    expect(h?.from).toBe('4')
    expect(h?.to).toBe('5 years')
  })
})
