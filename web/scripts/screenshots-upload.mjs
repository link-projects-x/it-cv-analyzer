// Screenshots of the upload screen states (idle, rejected, progress, error) at 1440px and 375px,
// plus an end-to-end check: upload -> results -> "New CV" -> upload.
// Needs a running server with the mock API (VITE_API_URL unset):
//   npm run build && npx vite preview --port 4173 &
//   node scripts/screenshots-upload.mjs [base-url]
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const base = process.argv[2] ?? 'http://localhost:4173/'
const outDir = fileURLToPath(new URL('../docs/screenshots/', import.meta.url))
mkdirSync(outDir, { recursive: true })

const viewports = [
  { name: '1440', width: 1440, height: 900 },
  { name: '375', width: 375, height: 812 },
]

const file = (name, mimeType) => ({ name, mimeType, buffer: Buffer.from('Example CV text') })

async function open(page) {
  await page.goto(base)
  await page.getByTestId('drop-zone').waitFor()
  await page.evaluate(() => document.fonts.ready)
}

const browser = await chromium.launch()
try {
  for (const vp of viewports) {
    // Reduced motion: the pulsing current-step mark is drawn static, so the frames are stable.
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, reducedMotion: 'reduce' })
    const page = await context.newPage()
    const shot = async (state) => {
      const path = `${outDir}upload-${state}-${vp.name}.png`
      await page.screenshot({ path, fullPage: true })
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
      console.log('saved', path, overflow ? '(HORIZONTAL OVERFLOW)' : '(no horizontal overflow)')
    }
    const input = () => page.getByLabel('CV file')

    await open(page)
    await shot('idle')

    await input().setInputFiles(file('photo.png', 'image/png'))
    await page.getByRole('alert').waitFor()
    await shot('rejected')

    await open(page)
    await input().setInputFiles(file('cv.pdf', 'application/pdf'))
    await page.locator('[aria-current="step"]', { hasText: 'Reading skills from the CV' }).waitFor()
    await shot('progress')

    // The same job continues to the results screen; "New CV" returns to upload.
    await page.getByTestId('summary').waitFor({ timeout: 15000 })
    await page.getByRole('button', { name: 'New CV' }).click()
    await page.getByTestId('drop-zone').waitFor()
    console.log(`flow check ${vp.name}: upload -> results -> New CV -> upload ok`)

    await open(page)
    await input().setInputFiles(file('fail-cv.pdf', 'application/pdf'))
    await page.getByRole('heading', { name: 'The CV could not be analyzed' }).waitFor({ timeout: 15000 })
    await shot('error')

    await context.close()
  }
} finally {
  await browser.close()
}
