import { describe, expect, it } from 'vitest'
import { dragSkill, initialState, salaryEstimate, setEnglish, setExperience } from './state'
import { profileResponse, salary } from './testData'

const start = () => initialState(profileResponse([{ id: 'python', level: 2 }], 2, 'B2'))

describe('salaryEstimate', () => {
  it('nothing moved: the point estimate', () => {
    expect(salaryEstimate(start(), salary())).toEqual({ kind: 'point', value: 2700, low: null, high: null })
  })

  it('nothing moved: low and high when the model returns them', () => {
    expect(salaryEstimate(start(), salary({ low: 2400, high: 3000 }))).toEqual({
      kind: 'point',
      value: 2700,
      low: 2400,
      high: 3000,
    })
  })

  it('skill sliders do not change the estimate', () => {
    expect(salaryEstimate(dragSkill(start(), 'python', 3), salary())).toEqual(salaryEstimate(start(), salary()))
  })

  it('only English moved: the grid value for the new level', () => {
    expect(salaryEstimate(setEnglish(start(), 'C1'), salary())).toEqual({ kind: 'grid', value: 3100, input: 'english' })
  })

  it('only experience moved: the grid value for the new years', () => {
    expect(salaryEstimate(setExperience(start(), 3), salary())).toEqual({
      kind: 'grid',
      value: 3030,
      input: 'experience_years',
    })
  })

  it('both moved: a dash, no added deltas', () => {
    const s = setExperience(setEnglish(start(), 'C1'), 3)
    expect(salaryEstimate(s, salary())).toEqual({ kind: 'none', reason: 'two-settings' })
  })

  it('moving one back to the opening value returns to the grid for the other', () => {
    const s = setEnglish(setExperience(setEnglish(start(), 'C1'), 3), 'B2')
    expect(salaryEstimate(s, salary())).toEqual({ kind: 'grid', value: 3030, input: 'experience_years' })
  })

  it('a missing grid key gives a dash, never the opening value', () => {
    expect(salaryEstimate(setEnglish(start(), 'C2'), salary())).toEqual({ kind: 'none', reason: 'missing-grid-key' })
    expect(salaryEstimate(setExperience(start(), 9), salary())).toEqual({ kind: 'none', reason: 'missing-grid-key' })
  })
})
