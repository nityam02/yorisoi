import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
const dir = new URL('./', import.meta.url).pathname
mkdirSync(`${dir}out/cards`, { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
await page.goto(`file://${dir}cards.html`)
await page.evaluate(() => document.fonts.ready)
await page.waitForTimeout(1500)
for (const id of ['s1_title', 's2_problem', 's7_how', 's8_close']) {
  await page.evaluate((id) => { document.querySelectorAll('.card').forEach((c) => c.classList.toggle('on', c.id === id)) }, id)
  await page.locator(`#${id}`).screenshot({ path: `${dir}out/cards/${id}.png` })
}
await browser.close()
