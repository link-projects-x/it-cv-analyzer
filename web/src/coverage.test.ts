import { describe, expect, it } from 'vitest'
import golden from '@contracts/fixtures/coverage-golden.json'
import { coverage, effectiveLevels } from './coverage'
import type { CoverageProfile, CoverageVacancy } from './types'

interface GoldenCase {
  name: string
  profile: CoverageProfile
  vacancy: CoverageVacancy
  expected: { coverage: number | null; fits: boolean }
}

const cases = golden as unknown as GoldenCase[]

describe('coverage parity with contracts/fixtures/coverage-golden.json', () => {
  it('has the 19 cases the reference writes', () => {
    expect(cases).toHaveLength(19)
  })

  it.each(cases.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    const got = coverage(c.profile, c.vacancy)
    if (c.expected.coverage === null) {
      expect(got.coverage).toBeNull()
    } else {
      expect(got.coverage).not.toBeNull()
      expect(Math.abs((got.coverage ?? NaN) - c.expected.coverage)).toBeLessThanOrEqual(1e-9)
    }
    expect(got.fits).toBe(c.expected.fits)
  })
})

describe('effectiveLevels', () => {
  it('lifts every ancestor to the child level', () => {
    expect(effectiveLevels({ 'aws-bedrock': 2 })).toEqual({ 'aws-bedrock': 2, aws: 2 })
  })

  it('keeps the parent own level when it is higher', () => {
    expect(effectiveLevels({ aws: 3, 'aws-bedrock': 1 })).toEqual({ aws: 3, 'aws-bedrock': 1 })
  })

  it('stops on a cycle in the catalog', () => {
    const catalog = [
      { id: 'a', name: 'A', group: 'g', parent: 'b', aliases: [] },
      { id: 'b', name: 'B', group: 'g', parent: 'a', aliases: [] },
    ]
    expect(effectiveLevels({ a: 2 }, catalog)).toEqual({ a: 2, b: 2 })
  })
})
