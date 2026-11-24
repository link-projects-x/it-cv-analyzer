// WCAG 2.x contrast of the colour tokens in tokens.css, light and dark.
// Run `npx vitest run src/styles/contrast.test.ts --reporter=verbose` to see the ratios.
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Read from disk: vitest does not process CSS imports by default.
const css = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8')

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`)
  if (start === -1) throw new Error(`no block ${selector}`)
  const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('}', start))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[m[1] as string] = (m[2] as string).trim()
  return out
}

const light = block(':root')
const darkMedia = block(':root:not([data-theme="light"])')
const dark = { ...light, ...block(':root[data-theme="dark"]') }

function resolve(theme: Record<string, string>, name: string): string {
  const v = theme[name]
  if (v === undefined) throw new Error(`no token ${name}`)
  const ref = /^var\((--[\w-]+)\)$/.exec(v)
  return ref ? resolve(theme, ref[1] as string) : v
}

function luminance(hex: string): number {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? [...h].map((c) => c + c).join('') : h
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(full.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

// [foreground, background]: text tokens on the page and card backgrounds, plus tokens the app
// uses as text colour (links, moved values, notes) and the filled chips / badge.
const PAIRS: [string, string][] = [
  ...['--color-text', '--color-text-strong', '--color-text-muted', '--color-primary', '--color-secondary'].flatMap(
    (fg): [string, string][] => [
      [fg, '--color-bg'],
      [fg, '--color-surface'],
    ],
  ),
  ['--color-on-primary', '--color-primary'],
  ['--color-on-primary', '--color-secondary'],
  ['--color-on-accent', '--color-accent'],
]

// Pairs that are known to fail AA 4.5:1. Empty since light --color-text-muted moved from #9ea1a1 to #6e7272.
const KNOWN_FAILURES = new Set<string>()

const AA = 4.5

describe('token contrast (WCAG AA, 4.5:1 for text)', () => {
  it('the prefers-color-scheme dark block equals the data-theme="dark" block', () => {
    expect(darkMedia).toEqual(block(':root[data-theme="dark"]'))
  })

  for (const [mode, theme] of [
    ['light', light],
    ['dark', dark],
  ] as const) {
    for (const [fg, bg] of PAIRS) {
      const key = `${mode} ${fg} ${bg}`
      const ratio = contrast(resolve(theme, fg), resolve(theme, bg))
      it(`${key}: ${ratio.toFixed(2)}`, () => {
        if (KNOWN_FAILURES.has(key)) expect(ratio).toBeLessThan(AA)
        else expect(ratio).toBeGreaterThanOrEqual(AA)
      })
    }
  }

  it('focus ring (--color-info) reaches 3:1 against bg and surface (non-text)', () => {
    for (const theme of [light, dark]) {
      for (const bg of ['--color-bg', '--color-surface']) {
        expect(contrast(resolve(theme, '--color-info'), resolve(theme, bg))).toBeGreaterThanOrEqual(3)
      }
    }
  })
})
