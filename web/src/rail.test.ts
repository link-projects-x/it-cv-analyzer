import { describe, expect, it } from 'vitest'
import { exampleResponse } from './data'
import { groupLabel, groupSliders, matchesSearch, shownSliderIds, sliderEffects, topSliderIds } from './rail'
import { initialState, openingProfile } from './state'
import { req, vac } from './testData'
import type { CoverageProfile, SkillDef } from './types'
import { visibleSkillSliders, type SkillSlider } from './visibility'

const catalog: SkillDef[] = [
  { id: 'python', name: 'Python', group: 'language', aliases: [] },
  { id: 'aws', name: 'AWS', group: 'cloud', aliases: [] },
  { id: 'aws-s3', name: 'AWS S3', group: 'cloud', parent: 'aws', aliases: [] },
  { id: 'gcp', name: 'GCP', group: 'cloud', aliases: [] },
  { id: 'gcp-vertex', name: 'Vertex AI', group: 'cloud', parent: 'gcp', aliases: [] },
]
const slider = (id: string, name: string): SkillSlider => ({ id, name, vacancies: 1, direct: 1 })
const sliders = [slider('python', 'Python'), slider('aws', 'AWS'), slider('aws-s3', 'AWS S3'), slider('gcp-vertex', 'Vertex AI')]
const empty: CoverageProfile = { skills: {}, experience_years: 0, english: null }

describe('sliderEffects', () => {
  it('sums the coverage change from level 0 to 3 over the vacancies', () => {
    const vs = [vac([req(['python'], 3), req(['aws'], 3)]), vac([req(['python'], 3)])]
    const e = sliderEffects(empty, vs, sliders, catalog)
    expect(e.python).toBeCloseTo(0.5 + 1, 12)
    expect(e.aws).toBeCloseTo(0.5, 12)
    // a child moves its parent's requirement
    expect(e['aws-s3']).toBeCloseTo(0.5, 12)
    expect(e['gcp-vertex']).toBe(0)
  })
})

describe('topSliderIds', () => {
  it('largest effect first; ties keep the slider order', () => {
    expect(topSliderIds(sliders, { python: 1, aws: 2, 'aws-s3': 1, 'gcp-vertex': 0 }, 3)).toEqual(['aws', 'python', 'aws-s3'])
  })
})

describe('groupSliders', () => {
  it('groups by skills.json group, children under their parent, groups by largest effect', () => {
    const groups = groupSliders(sliders, { python: 1, aws: 2, 'aws-s3': 3, 'gcp-vertex': 0.5 }, catalog)
    expect(groups.map((g) => g.id)).toEqual(['cloud', 'language'])
    expect(groups[0]?.items.map((i) => [i.slider.id, i.parent])).toEqual([
      ['aws', null],
      ['aws-s3', 'aws'],
      // gcp has no slider, so Vertex AI is not indented
      ['gcp-vertex', null],
    ])
  })
})

describe('search and expanded set', () => {
  it('matchesSearch is a case-insensitive substring match on the name or an alias', () => {
    expect(matchesSearch(['AWS S3'], 's3')).toBe(true)
    expect(matchesSearch(['AWS S3'], '  ')).toBe(true)
    expect(matchesSearch(['Python'], 'aws')).toBe(false)
    expect(matchesSearch(['Google Cloud', 'gcp'], 'GCP')).toBe(true)
  })

  it('top plus moved by default, all with showAll, matches while searching', () => {
    const base = { query: '', showAll: false, top: ['python'], moved: ['gcp-vertex'] }
    expect([...shownSliderIds(sliders, base)]).toEqual(['python', 'gcp-vertex'])
    expect(shownSliderIds(sliders, { ...base, showAll: true }).size).toBe(4)
    expect([...shownSliderIds(sliders, { ...base, query: 'aws' }, catalog)]).toEqual(['aws', 'aws-s3'])
    const withAlias = catalog.map((s) => (s.id === 'gcp-vertex' ? { ...s, aliases: ['vertex', 'gcp vertex'] } : s))
    expect([...shownSliderIds(sliders, { ...base, query: 'gcp' }, withAlias)]).toEqual(['gcp-vertex'])
  })

  it('group labels fall back to the id', () => {
    expect(groupLabel('llm')).toBe('LLM')
    expect(groupLabel('new-group')).toBe('new-group')
  })
})

describe('example response', () => {
  const state = initialState(exampleResponse)
  const vacancies = exampleResponse.vacancies.map((v) => v.vacancy)
  const all = visibleSkillSliders(openingProfile(state), vacancies)
  const effects = sliderEffects(openingProfile(state), vacancies, all)

  it('29 skill sliders, 8 expanded by default, every slider in exactly one group', () => {
    expect(all).toHaveLength(29)
    expect(topSliderIds(all, effects)).toHaveLength(8)
    const grouped = groupSliders(all, effects).flatMap((g) => g.items.map((i) => i.slider.id))
    expect(grouped.sort()).toEqual(all.map((s) => s.id).sort())
  })
})
