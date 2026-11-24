import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { App } from './App'
import { exampleResponse } from './data'

describe('App with the example response (static render)', () => {
  const html = renderToStaticMarkup(<App response={exampleResponse} />)

  it('draws experience, English and the 29 skill sliders', () => {
    expect(html.match(/type="range"/g)).toHaveLength(31)
  })

  it('sets aria-valuetext to the level name', () => {
    expect(html).toContain('id="slider-python"')
    expect(html).toMatch(/aria-valuetext="2 years"[^>]*id="slider-python"|id="slider-python"[^>]*aria-valuetext="2 years"/)
  })

  it('opening state: Reset disabled, point salary, the skill note, 0 fits', () => {
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Reset<\/button>/)
    expect(html).toContain('2,700 USD')
    expect(html).toContain('Skill sliders do not change the salary estimate')
    expect(html).toContain('Fits: <strong>0</strong> of 2 vacancies')
    expect(html).not.toContain(' pp</span>')
  })

  it('lists vacancies by coverage with percentages', () => {
    const first = html.indexOf('Middle AI Engineer')
    const second = html.indexOf('ML Engineer (Computer Vision)')
    expect(first).toBeGreaterThan(-1)
    expect(second).toBeGreaterThan(first)
    // coverage-golden.json: example vacancy 1 0.4118, vacancy 2 0.2833
    expect(html).toContain('>41%<')
    expect(html).toContain('>28%<')
  })
})
