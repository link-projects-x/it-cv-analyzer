// Screenshots of the results screen at 1440px and 375px, light and dark.
// Needs a running server: `npm run dev -- --port 5180`, then `node scripts/screenshots.mjs [url]`.
// Writes web/docs/screenshots/results-<width>-<theme>[-moved|-sheet].png.
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'

const url = process.argv[2] ?? 'http://localhost:5180/'
const outDir = fileURLToPath(new URL('../docs/screenshots/', import.meta.url))
mkdirSync(outDir, { recursive: true })

const browser = await chromium.launch()
const problems = []
for (const width of [1440, 375]) {
  for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({
      viewport: { width, height: width === 1440 ? 1000 : 812 },
      colorScheme: theme,
      deviceScaleFactor: 1,
    })
    const page = await context.newPage()
    page.on('pageerror', (e) => problems.push(`${width} ${theme}: ${e.message}`))
    await page.goto(url, { waitUntil: 'networkidle' })
    await page.evaluate(() => document.fonts.ready)
    // open the first vacancy's requirement list so the evidence quotes are in the picture
    await page.locator('details.reqs').first().evaluate((d) => (d.open = true))
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    if (scrollWidth > width) problems.push(`${width} ${theme}: horizontal scroll, scrollWidth ${scrollWidth}`)
    await page.screenshot({ path: `${outDir}results-${width}-${theme}.png`, fullPage: true })
    if (width >= 1024) {
      // moved state: Python one step up (above the CV tick), English one step up, keyboard only
      await page.locator('details.reqs').first().evaluate((d) => (d.open = false))
      await page.getByLabel('Python').focus()
      await page.keyboard.press('ArrowRight')
      await page.getByLabel('English').focus()
      await page.keyboard.press('ArrowRight')
      await page.screenshot({ path: `${outDir}results-${width}-${theme}-moved.png` })
    }
    if (width < 1024) {
      await page.getByRole('button', { name: /Adjust profile/ }).click()
      await page.waitForTimeout(300)
      await page.screenshot({ path: `${outDir}results-${width}-${theme}-sheet.png` })
    }
    await context.close()
  }
}
await browser.close()
if (problems.length > 0) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log(`screenshots written to ${outDir}`)
