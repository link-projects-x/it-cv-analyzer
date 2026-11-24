import { describe, expect, it } from 'vitest'
import {
  coverages,
  currentProfile,
  cvSupportedLevel,
  cvTick,
  dragSkill,
  fitsCount,
  initialState,
  isTouched,
  meanCoverage,
  reset,
  setEnglish,
  setExperience,
} from './state'
import { profileResponse, req, vac } from './testData'

const start = () =>
  initialState(
    profileResponse([
      { id: 'python', level: 2 },
      { id: 'docker', level: 2, evidence: null },
    ], 2, 'B2'),
  )

describe('initialState', () => {
  it('takes opening values from the profile and starts with nothing touched', () => {
    const s = start()
    expect(s.opening.skills).toEqual({ python: 2, docker: 2 })
    expect(s.opening.experienceYears).toBe(2)
    expect(s.opening.english).toBe('B2')
    expect(s.touched).toEqual({ skills: {} })
    expect(isTouched(s)).toBe(false)
  })
})

describe('transitions', () => {
  it('dragSkill records the new level and does not change the opening', () => {
    const s = dragSkill(start(), 'python', 3)
    expect(s.touched.skills).toEqual({ python: 3 })
    expect(s.opening.skills.python).toBe(2)
    expect(currentProfile(s).skills.python).toBe(3)
    expect(isTouched(s)).toBe(true)
  })

  it('dragging back to the opening level removes the skill from touched', () => {
    const s = dragSkill(dragSkill(start(), 'python', 3), 'python', 2)
    expect(s.touched.skills).toEqual({})
    expect(isTouched(s)).toBe(false)
  })

  it('a skill missing from the profile opens at 0; back to 0 removes it', () => {
    const s1 = dragSkill(start(), 'rag', 2)
    expect(s1.touched.skills).toEqual({ rag: 2 })
    expect(dragSkill(s1, 'rag', 0).touched.skills).toEqual({})
  })

  it('dragSkill clamps to the slider range from coverage.json', () => {
    expect(dragSkill(start(), 'rag', 12).touched.skills).toEqual({ rag: 10 })
    expect(dragSkill(start(), 'python', -1).touched.skills).toEqual({ python: 0 })
  })

  it('setExperience and back', () => {
    const s = setExperience(start(), 5)
    expect(s.touched.experienceYears).toBe(5)
    expect(currentProfile(s).experience_years).toBe(5)
    const back = setExperience(s, 2)
    expect('experienceYears' in back.touched).toBe(false)
    expect(isTouched(back)).toBe(false)
  })

  it('setExperience rounds to the step and clamps to the range', () => {
    expect(setExperience(start(), 40).touched.experienceYears).toBe(15)
    expect(setExperience(start(), 3.4).touched.experienceYears).toBe(3)
  })

  it('setEnglish and back', () => {
    const s = setEnglish(start(), 'C1')
    expect(currentProfile(s).english).toBe('C1')
    expect(isTouched(s)).toBe(true)
    expect(isTouched(setEnglish(s, 'B2'))).toBe(false)
  })

  it('setEnglish from a profile without English', () => {
    const s0 = initialState(profileResponse([], 2, null))
    const s1 = setEnglish(s0, 'B1')
    expect(currentProfile(s1).english).toBe('B1')
    expect(isTouched(setEnglish(s1, null))).toBe(false)
  })

  it('reset returns to the opening state', () => {
    const s = setEnglish(setExperience(dragSkill(start(), 'rag', 3), 6), 'C2')
    const r = reset(s)
    expect(r.touched).toEqual({ skills: {} })
    expect(currentProfile(r)).toEqual(currentProfile(start()))
  })

  it('transitions do not mutate the input state', () => {
    const s = start()
    const snapshot = JSON.stringify(s)
    dragSkill(s, 'python', 3)
    setExperience(s, 9)
    setEnglish(s, 'A1')
    expect(JSON.stringify(s)).toBe(snapshot)
  })
})

describe('selectors', () => {
  const vacancies = [vac([req(['python'], 3)]), vac([req(['python'], 2)]), vac([])]

  it('coverages, fitsCount and meanCoverage follow the current profile', () => {
    const s = start()
    expect(coverages(s, vacancies).map((c) => c.coverage)).toEqual([2 / 3, 1, null])
    expect(fitsCount(s, vacancies)).toBe(1)
    // the vacancy with coverage null is left out of the mean
    expect(meanCoverage(coverages(s, vacancies))).toBeCloseTo((2 / 3 + 1) / 2, 12)
    expect(fitsCount(dragSkill(s, 'python', 3), vacancies)).toBe(2)
  })

  it('CV tick only for skills with evidence', () => {
    const s = start()
    expect(cvTick(s, 'python')).toBe(2)
    expect(cvTick(s, 'docker')).toBeNull()
    expect(cvTick(s, 'rag')).toBeNull()
    expect(cvSupportedLevel(s, 'python')).toBe(2)
    expect(cvSupportedLevel(s, 'docker')).toBe(0)
  })
})
