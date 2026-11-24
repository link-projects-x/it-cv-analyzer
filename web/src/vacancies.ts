// Rows of the vacancy list and their order.

export interface VacancyRow {
  id: string
  url: string
  title: string
  company: string
  similarity: number
  coverage: number | null
  openingCoverage: number | null
  fits: boolean
}

// Coverage descending, then similarity descending; coverage null goes last.
export function sortVacancyRows(rows: VacancyRow[]): VacancyRow[] {
  return [...rows].sort((a, b) => {
    if (a.coverage === null || b.coverage === null) {
      if (a.coverage !== b.coverage) return a.coverage === null ? 1 : -1
    } else if (a.coverage !== b.coverage) {
      return b.coverage - a.coverage
    }
    return b.similarity - a.similarity
  })
}
