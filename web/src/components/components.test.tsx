// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { exampleResponse } from '../data'
import { requirementChecks } from '../requirements'
import { req, vac } from '../testData'
import { App } from '../App'
import { Delta } from './Delta'
import { StatCards } from './StatCards'
import { ChipLegend, SkillChips } from './VacancyList'

afterEach(cleanup)

describe('Delta colouring', () => {
  it('positive, negative and zero get their own class', () => {
    render(
      <>
        <Delta value={2} />
        <Delta value={-1.25} digits={1} unit="pp" />
        <Delta value={0.04} digits={1} />
      </>,
    )
    expect(screen.getByText('+2').className).toContain('delta-positive')
    expect(screen.getByText('-1.3 pp').className).toContain('delta-negative')
    expect(screen.getByText('0.0').className).toContain('delta-zero')
  })

  it('stat cards show deltas only after a move, coloured by sign', () => {
    const current = { fits: 1, total: 2, mean: 0.5, salary: { kind: 'grid' as const, value: 2300, input: 'english' as const } }
    const { rerender } = render(
      <StatCards current={current} delta={{ fits: 1, meanPp: -3.2, salary: -400 }} touched={false} modelVersion="m" />,
    )
    expect(screen.getByTestId('stat-fits').querySelector('.delta')).toBeNull()

    rerender(<StatCards current={current} delta={{ fits: 1, meanPp: -3.2, salary: -400 }} touched modelVersion="m" />)
    expect(within(screen.getByTestId('stat-fits')).getByText('+1').dataset.sign).toBe('positive')
    expect(within(screen.getByTestId('stat-mean')).getByText('-3.2 pp').dataset.sign).toBe('negative')
    expect(within(screen.getByTestId('stat-salary')).getByText('-400 USD').dataset.sign).toBe('negative')
  })
})

describe('skill chips', () => {
  const profile = { skills: { python: 3, gcp: 1 }, experience_years: 2, english: null }
  const v = vac([req(['python'], 3), req(['aws', 'gcp'], 2), req(['rag'], 2), req(['docker'], 1, false)])

  it('one chip per required skill, with covered / partial / missing state', () => {
    render(<SkillChips checks={requirementChecks(profile, v)} />)
    const chips = screen.getAllByRole('listitem')
    expect(chips.map((c) => c.dataset.status)).toEqual(['covered', 'partial', 'missing'])
    expect(chips[0]?.className).toContain('chip-covered')
    expect(chips[1]?.className).toContain('chip-partial')
    expect(chips[2]?.className).toContain('chip-missing')
    expect(chips[1]?.textContent).toBe('AWS / Google Cloud: partly covered')
  })

  it('the legend names the three states', () => {
    render(<ChipLegend />)
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['covered', 'partly covered', 'missing'])
  })
})

describe('results screen with the example response', () => {
  const visibleSkillRows = () =>
    [...document.querySelectorAll<HTMLElement>('.skill-rail [data-slider]')].filter((el) => !el.hidden)

  it('8 skill sliders expanded, "Show all 29" expands, search filters by name', () => {
    render(<App response={exampleResponse} />)
    expect(document.querySelectorAll('input[type="range"]')).toHaveLength(31)
    expect(visibleSkillRows()).toHaveLength(8)

    fireEvent.click(screen.getByRole('button', { name: 'Show all 29' }))
    expect(visibleSkillRows()).toHaveLength(29)
    fireEvent.click(screen.getByRole('button', { name: 'Show top 8' }))
    expect(visibleSkillRows()).toHaveLength(8)

    fireEvent.change(screen.getByLabelText('Search skills'), { target: { value: 'pinecone' } })
    expect(visibleSkillRows().map((el) => el.dataset.slider)).toEqual(['pinecone'])
    // aliases count: "ec2" finds "Amazon EC2"
    fireEvent.change(screen.getByLabelText('Search skills'), { target: { value: 'ec2' } })
    expect(visibleSkillRows().map((el) => el.querySelector('label')?.textContent)).toEqual(['Amazon EC2'])
    expect(screen.queryByRole('button', { name: /Show all/ })).toBeNull()
    // experience and English stay pinned
    expect(screen.getByLabelText('Experience')).toBeTruthy()
    expect(screen.getByLabelText('English')).toBeTruthy()
  })

  it('Reset is disabled until a slider moves; a move shows "was" and coloured deltas', () => {
    render(<App response={exampleResponse} />)
    const resetBtn = screen.getByRole('button', { name: 'Reset' }) as HTMLButtonElement
    expect(resetBtn.disabled).toBe(true)

    fireEvent.change(screen.getByLabelText('Python'), { target: { value: '3' } })
    expect(resetBtn.disabled).toBe(false)
    const row = document.querySelector<HTMLElement>('[data-slider="python"]')
    expect(row?.textContent).toContain('was 2 years')
    expect(row?.className).toContain('above')
    expect(within(screen.getByTestId('stat-mean')).getByText(/pp$/).dataset.sign).toBe('positive')

    fireEvent.click(resetBtn)
    expect(resetBtn.disabled).toBe(true)
  })
})
