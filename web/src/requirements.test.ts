import { describe, expect, it } from 'vitest'
import { coverage } from './coverage'
import { checkStatus, requirementChecks } from './requirements'
import { req, vac } from './testData'
import type { CoverageProfile } from './types'

const profile = (skills: Record<string, number>, years = 2, english: CoverageProfile['english'] = 'B1'): CoverageProfile => ({
  skills,
  experience_years: years,
  english,
})

describe('checkStatus', () => {
  it('covered at 1, partial above 0, missing at 0', () => {
    expect(checkStatus(1)).toBe('covered')
    expect(checkStatus(0.5)).toBe('partial')
    expect(checkStatus(0)).toBe('missing')
  })
})

describe('requirementChecks', () => {
  const v = vac([req(['python'], 3), req(['aws', 'gcp'], 2), req(['rag'], 2, false)], 4, 'B2')

  it('one check per requirement, then experience and English', () => {
    const checks = requirementChecks(profile({ python: 3, gcp: 1 }), v)
    expect(checks.map((c) => [c.kind, c.status])).toEqual([
      ['skill', 'covered'],
      ['skill', 'partial'],
      ['skill', 'missing'],
      ['experience', 'partial'],
      ['english', 'partial'],
    ])
    const cloud = checks[1]
    expect(cloud?.kind === 'skill' && cloud.level).toBe(1)
  })

  it('a child skill counts for its parent (hierarchy)', () => {
    const [cloud] = requirementChecks(profile({ 'aws-bedrock': 2 }), vac([req(['aws'], 2)]))
    expect(cloud?.status).toBe('covered')
  })

  it('weighted scores add up to coverage()', () => {
    const p = profile({ python: 2, aws: 2 }, 3, 'B2')
    const checks = requirementChecks(p, v)
    let sum = 0
    let max = 0
    for (const c of checks) {
      const w = c.kind === 'skill' ? (c.required ? 2 : 1) : c.kind === 'experience' ? 2 : 1
      sum += w * c.score
      max += w
    }
    expect(sum / max).toBeCloseTo(coverage(p, v).coverage ?? NaN, 12)
  })

  it('no experience or English parts when the vacancy does not ask', () => {
    expect(requirementChecks(profile({}), vac([req(['python'], 1)]))).toHaveLength(1)
  })
})
