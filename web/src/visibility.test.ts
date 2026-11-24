import { describe, expect, it } from 'vitest'
import { exampleResponse } from './data'
import { initialState, openingProfile } from './state'
import { profileResponse, req, vac } from './testData'
import { visibleSkillSliders } from './visibility'

const ids = (p: ReturnType<typeof visibleSkillSliders>) => p.map((s) => s.id)
const profile = (skills: { id: string; level: number }[]) => openingProfile(initialState(profileResponse(skills)))

describe('visibleSkillSliders', () => {
  it('shows only skills that change the coverage of a loaded vacancy', () => {
    const got = ids(visibleSkillSliders(profile([]), [vac([req(['rag'], 2)])]))
    expect(got).toEqual(['rag'])
  })

  it('a profile child skill moves a vacancy that requires the parent', () => {
    const got = ids(visibleSkillSliders(profile([]), [vac([req(['aws'], 2)])]))
    expect(got).toContain('aws')
    expect(got).toContain('aws-bedrock')
    expect(got).not.toContain('azure')
  })

  it('a parent does not move a vacancy that requires a child', () => {
    const got = ids(visibleSkillSliders(profile([]), [vac([req(['pgvector'], 2)])]))
    expect(got).toEqual(['pgvector'])
  })

  it('a skill already covered through a child moves nothing and is not drawn', () => {
    // postgresql at 3 lifts sql to 3, so sql 0 -> 3 changes nothing
    const got = ids(visibleSkillSliders(profile([{ id: 'postgresql', level: 3 }]), [vac([req(['sql'], 2)])]))
    expect(got).toEqual(['postgresql'])
  })

  it('any_of: an option is hidden while another option already scores 1', () => {
    const got = ids(visibleSkillSliders(profile([{ id: 'docker', level: 3 }]), [vac([req(['docker', 'kubernetes'], 2)])]))
    expect(got).toEqual(['docker'])
  })

  it('orders by the number of vacancies the skill moves', () => {
    const got = ids(
      visibleSkillSliders(profile([]), [vac([req(['rag'], 2), req(['python'], 2)]), vac([req(['python'], 1)])]),
    )
    expect(got).toEqual(['python', 'rag'])
  })

  it('a vacancy with nothing to score moves no slider', () => {
    expect(visibleSkillSliders(profile([]), [vac([])])).toEqual([])
  })

  it('example response: 29 sliders, Python first (moves both vacancies)', () => {
    const s = initialState(exampleResponse)
    const got = visibleSkillSliders(openingProfile(s), exampleResponse.vacancies.map((v) => v.vacancy))
    expect(got).toHaveLength(29)
    expect(got[0]).toMatchObject({ id: 'python', vacancies: 2, direct: 2 })
    expect(ids(got)).not.toContain('typescript')
    expect(ids(got)).not.toContain('vector-db')
  })
})
