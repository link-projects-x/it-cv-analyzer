import { describe, expect, it } from 'vitest'
import { dragSkill, initialState, setEnglish, setExperience } from './state'
import { openingSummary, summary, summaryDelta } from './summary'
import { profileResponse, req, salary, vac } from './testData'

const start = () => initialState(profileResponse([{ id: 'python', level: 2 }], 2, 'B2'))
const vacancies = [vac([req(['python'], 3)]), vac([req(['python'], 2)]), vac([])]

describe('summary', () => {
  it('fits, total, mean and the salary estimate', () => {
    const s = summary(start(), vacancies, salary())
    expect(s.fits).toBe(1)
    expect(s.total).toBe(3)
    expect(s.mean).toBeCloseTo((2 / 3 + 1) / 2, 12)
    expect(s.salary).toEqual({ kind: 'point', value: 2700, low: null, high: null })
  })

  it('openingSummary ignores moved sliders', () => {
    const moved = dragSkill(start(), 'python', 3)
    expect(openingSummary(moved, vacancies, salary())).toEqual(summary(start(), vacancies, salary()))
  })
})

describe('summaryDelta', () => {
  it('zero at the opening state', () => {
    const s = summary(start(), vacancies, salary())
    expect(summaryDelta(s, s)).toEqual({ fits: 0, meanPp: 0, salary: 0 })
  })

  it('fits and mean coverage change with a skill; salary does not', () => {
    const moved = dragSkill(start(), 'python', 3)
    const d = summaryDelta(summary(moved, vacancies, salary()), openingSummary(moved, vacancies, salary()))
    expect(d.fits).toBe(1)
    expect(d.meanPp).toBeCloseTo(((1 + 1) / 2 - (2 / 3 + 1) / 2) * 100, 9)
    expect(d.salary).toBe(0)
  })

  it('salary delta follows the grid; null when the estimate is a dash', () => {
    const eng = setEnglish(start(), 'C1')
    expect(summaryDelta(summary(eng, vacancies, salary()), openingSummary(eng, vacancies, salary())).salary).toBe(400)
    const both = setExperience(eng, 3)
    expect(summaryDelta(summary(both, vacancies, salary()), openingSummary(both, vacancies, salary())).salary).toBeNull()
  })
})
