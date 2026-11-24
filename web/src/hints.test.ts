import { describe, expect, it } from 'vitest'
import { exampleResponse } from './data'
import { hints, hintText, rankedHints, signed } from './hints'
import { initialState, openingProfile, setEnglish, setExperience } from './state'
import { profileResponse, req, salary, vac } from './testData'
import { visibleSkillSliders } from './visibility'

// With an empty grid every English / experience step gives a dash, so only skill hints remain.
const NO_GRID = salary({ grid: { english: {}, experience_years: {}, company_type: {}, domains: {} } })

describe('rankedHints', () => {
  it('ranks by fits change first, then mean coverage change', () => {
    const s = initialState(profileResponse([{ id: 'python', level: 2 }], 2, 'B2'))
    // python 2 -> 3: vacancy 1 goes 2/3 -> 1 and fits (+1 fits, +16.7 pp mean);
    // rag 0 -> 1: vacancy 2 goes 0 -> 0.5 (+25 pp mean) and fits nothing
    const vacancies = [vac([req(['python'], 3), req(['python'], 3)]), vac([req(['rag'], 1), req(['kubernetes'], 1)])]
    const got = rankedHints(s, vacancies, NO_GRID, ['rag', 'python'])
    expect(got.map((h) => h.key)).toEqual(['skill:python', 'skill:rag'])
    expect(got[0]?.fitsDelta).toBe(1)
    expect(got[0]?.coverageDeltaPp).toBeCloseTo((1 / 3 / 2) * 100, 9)
    expect(got[1]?.fitsDelta).toBe(0)
    expect(got[1]?.coverageDeltaPp).toBeCloseTo(25, 9)
  })

  it('equal fits change: larger mean coverage change first', () => {
    const s = initialState(profileResponse([], 2, 'B2'))
    const vacancies = [vac([req(['rag'], 3), req(['docker'], 1), req(['docker'], 1)])]
    const got = rankedHints(s, vacancies, NO_GRID, ['rag', 'docker'])
    expect(got.map((h) => h.key)).toEqual(['skill:docker', 'skill:rag'])
    expect(got[0]?.coverageDeltaPp).toBeCloseTo(((2 * 1 + 2 * 1) / 6) * 100, 9)
  })

  it('equal fits and coverage change: larger salary change first', () => {
    const s = initialState(profileResponse([], 2, 'B2'))
    // no vacancy asks for experience or English, so only the salary differs
    const vacancies = [vac([req(['rag'], 1)])]
    const got = rankedHints(s, vacancies, salary(), [])
    expect(got.map((h) => [h.key, h.salaryDelta])).toEqual([
      ['english', 400],
      ['experience', 330],
    ])
  })

  it('drops steps that change nothing and skills already at the maximum', () => {
    const s = initialState(profileResponse([{ id: 'python', level: 3 }], 2, 'B2'))
    const vacancies = [vac([req(['python'], 2), req(['docker'], 3)])]
    const got = rankedHints(s, vacancies, NO_GRID, ['python', 'docker'])
    expect(got.map((h) => h.key)).toEqual(['skill:docker'])
  })

  it('salary change is null when the grid rules give a dash after the step', () => {
    const s = setEnglish(initialState(profileResponse([], 2, 'B2')), 'C1')
    const vacancies = [vac([], 3)]
    const exp = rankedHints(s, vacancies, salary(), []).find((h) => h.key === 'experience')
    expect(exp?.salaryDelta).toBeNull()
    expect(exp?.coverageDeltaPp).toBeCloseTo((1 - 2 / 3) * 100, 9)
  })

  it('salary change from the grid when only that input is moved', () => {
    const s = setExperience(initialState(profileResponse([], 2, 'B2')), 1)
    const exp = rankedHints(s, [vac([])], salary(), []).find((h) => h.key === 'experience')
    // 1 -> 2 years returns experience to the opening value, so the estimate after the step is the point
    expect(exp?.salaryDelta).toBe(2700 - 2370)
  })

  it('salary change is measured between the displayed estimates (point -> grid)', () => {
    // grid at the opening position (2 years: 2500) differs from the point (2700)
    const sal = salary({ grid: { english: {}, experience_years: { '2': 2500, '3': 2800 }, company_type: {}, domains: {} } })
    const exp = rankedHints(initialState(profileResponse([], 2, 'B2')), [vac([])], sal, []).find((h) => h.key === 'experience')
    expect(exp?.salaryDelta).toBe(2800 - 2700)
  })

  it('hints() keeps the top 5', () => {
    const s = initialState(exampleResponse)
    const vacancies = exampleResponse.vacancies.map((v) => v.vacancy)
    const ids = visibleSkillSliders(openingProfile(s), vacancies).map((x) => x.id)
    const all = rankedHints(s, vacancies, exampleResponse.salary, ids)
    const top = hints(s, vacancies, exampleResponse.salary, ids)
    expect(all.length).toBeGreaterThan(5)
    expect(top).toEqual(all.slice(0, 5))
    expect(top.map((h) => h.text)).toEqual([
      'Python: 2 years → 3 years: 0 vacancies, +3.6 pp',
      'Amazon EC2: none → 1 year: 0 vacancies, +2.8 pp',
      'Amazon SageMaker: none → 1 year: 0 vacancies, +2.8 pp',
      'AWS: none → 1 year: 0 vacancies, +2.0 pp',
      'Docker: 2 years → 3 years: 0 vacancies, +2.0 pp',
    ])
  })
})

describe('hint text', () => {
  it('matches the format in the brief', () => {
    expect(
      hintText({ label: 'RAG', from: 'pet project', to: 'production', fitsDelta: 3, coverageDeltaPp: 4.06, salaryDelta: null }),
    ).toBe('RAG: pet project → production: +3 vacancies, +4.1 pp')
  })

  it('adds the salary change when there is one', () => {
    expect(
      hintText({ label: 'English', from: 'B2', to: 'C1', fitsDelta: 1, coverageDeltaPp: 0, salaryDelta: 400 }),
    ).toBe('English: B2 → C1: +1 vacancy, 0.0 pp, +400 USD/month')
  })

  it('signed() prints no sign for values that round to zero', () => {
    expect(signed(-0.04, 1)).toBe('0.0')
    expect(signed(2)).toBe('+2')
    expect(signed(-2)).toBe('-2')
  })
})
