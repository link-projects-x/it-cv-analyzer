import { describe, expect, it } from 'vitest'
import { gradeFits, isEngineeringTitle } from './localApi'

describe('gradeFits', () => {
  it('keeps vacancies within one grade of the CV', () => {
    expect(gradeFits('senior', 'middle')).toBe(true)
    expect(gradeFits('senior', 'senior')).toBe(true)
    expect(gradeFits('senior', 'lead')).toBe(true)
    expect(gradeFits('senior', 'junior')).toBe(false)
    expect(gradeFits('senior', 'intern')).toBe(false)
    expect(gradeFits('junior', 'senior')).toBe(false)
    expect(gradeFits('junior', 'intern')).toBe(true)
  })

  it('drops sales and management titles, keeps engineering ones', () => {
    expect(isEngineeringTitle('B2B Sales Executive / Sales Lead (IT Services / AI Consulting)')).toBe(false)
    expect(isEngineeringTitle('AI Delivery Manager')).toBe(false)
    expect(isEngineeringTitle('Senior business development manager (B2B, AI та finance сфера)')).toBe(false)
    expect(isEngineeringTitle('Applied AI Engineer (FDE)')).toBe(true)
    expect(isEngineeringTitle('Full-Stack JavaScript Developer (AI Products)')).toBe(true)
    expect(isEngineeringTitle('HRIS Developer')).toBe(true)
  })

  it('keeps vacancies with no grade stated', () => {
    expect(gradeFits('senior', 'unknown')).toBe(true)
    expect(gradeFits('senior', undefined)).toBe(true)
  })
})
