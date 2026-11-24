import { describe, expect, it } from 'vitest'
import { sortVacancyRows, type VacancyRow } from './vacancies'

const row = (id: string, coverage: number | null, similarity: number): VacancyRow => ({
  id,
  url: `https://example.test/${id}`,
  title: id,
  company: 'Example Co',
  similarity,
  coverage,
  openingCoverage: coverage,
  fits: false,
})

describe('sortVacancyRows', () => {
  it('coverage descending, then similarity descending, null coverage last', () => {
    const rows = [row('a', null, 0.99), row('b', 0.5, 0.1), row('c', 0.9, 0.2), row('d', 0.5, 0.7), row('e', null, 0.3)]
    expect(sortVacancyRows(rows).map((r) => r.id)).toEqual(['c', 'd', 'b', 'a', 'e'])
  })
})
