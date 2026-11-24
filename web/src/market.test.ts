import { describe, expect, it } from 'vitest'
import { marketRows } from './market'
import { req, vac } from './testData'

describe('marketRows', () => {
  const vacancies = [
    vac([req(['python'], 3), req(['docker'], 2), req(['aws', 'gcp'], 2)]),
    vac([req(['python'], 5), req(['kubernetes'], 2)]),
    vac([req(['python'], 4), req(['docker'], 2, false)]),
  ]

  it('counts required skills once per vacancy, with the median of the years asked', () => {
    const rows = marketRows(vacancies, { python: 4 })
    const python = rows.find((r) => r.key === 'python')!
    expect(python.vacancies).toBe(3)
    expect(python.share).toBe(1)
    expect(python.medianYears).toBe(4)
    expect(python.status).toBe('covered')
    // optional requirements are not counted
    expect(rows.find((r) => r.key === 'docker')!.vacancies).toBe(1)
  })

  it('keeps alternatives as one row and puts gaps first', () => {
    const rows = marketRows(vacancies, { python: 2, gcp: 3 })
    expect(rows.map((r) => [r.key, r.status])).toEqual([
      ['docker', 'missing'],
      ['kubernetes', 'missing'],
      ['python', 'partial'],
      ['aws|gcp', 'covered'],
    ])
    expect(rows.find((r) => r.key === 'aws|gcp')!.label).toBe('AWS / Google Cloud')
  })
})
