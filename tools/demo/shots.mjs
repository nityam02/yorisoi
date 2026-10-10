// Quick visual check: screenshots of each step for one resident.
import { chromium } from 'playwright'
const out = process.argv[2] ?? '.'
const base = process.env.BASE ?? 'http://localhost:8080'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1366, height: 900 }, deviceScaleFactor: 1 })
await page.goto(`${base}/#/R001`)
await page.waitForSelector('.gauge', { timeout: 60000 })
await page.waitForTimeout(2500) // map tiles
await page.screenshot({ path: `${out}/1-hazard.png` })
await page.getByRole('button', { name: 'Start the conversation' }).click()
await page.getByRole('button', { name: 'Use sample conversation' }).click()
await page.screenshot({ path: `${out}/2-conversation.png` })
await browser.close()
