// Records the four app segments of the demo video against the running app (real Gemini calls).
// Usage: node record.mjs   (server on http://localhost:8080; writes out/video/<segment>.webm + out/video/marks.json)
import { chromium } from 'playwright'
import { mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs'

const BASE = process.env.BASE ?? 'http://localhost:8080'
const RID = 'R001'
const SIZE = { width: 1600, height: 900 }
const OUT = new URL('./out/video/', import.meta.url).pathname
const durations = JSON.parse(readFileSync(new URL('./out/audio/durations.json', import.meta.url)))
rmSync(OUT, { recursive: true, force: true })
mkdirSync(OUT, { recursive: true })

// A visible cursor, since headless recordings show none.
const CURSOR = `
  window.addEventListener('DOMContentLoaded', () => {
    const c = document.createElement('div');
    c.id = '__cursor';
    c.style.cssText = 'position:fixed;z-index:99999;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
      'background:rgba(29,43,54,.35);border:2px solid #fff;box-shadow:0 0 0 1px rgba(29,43,54,.5);pointer-events:none;' +
      'transition:transform .12s;left:-50px;top:-50px';
    document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { c.style.transform = 'scale(.7)'; }, true);
    addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; }, true);
  });`

const browser = await chromium.launch()
const marks = {}

async function segment(id, fn) {
  const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } })
  await ctx.addInitScript(CURSOR)
  const page = await ctx.newPage()
  const t0 = Date.now()
  const mark = (name) => { (marks[id] ??= {})[name] = (Date.now() - t0) / 1000 }
  await fn(page, mark)
  mark('end')
  await ctx.close()
  const file = readdirSync(OUT).find((f) => f.endsWith('.webm') && !f.startsWith('s'))
  renameSync(OUT + file, `${OUT}${id}.webm`)
  console.log(id, JSON.stringify(marks[id]))
}

const pause = (page, s) => page.waitForTimeout(s * 1000)
async function click(page, locator, { wait = 0.35 } = {}) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 18 })
  await pause(page, wait)
  await locator.click()
}

await (await browser.newPage()).request.delete(`${BASE}/api/residents/${RID}/plan`)

// s3: worklist ranked by risk, then the hazard brief.
await segment('s3_hazard', async (page, mark) => {
  await page.goto(`${BASE}/`)
  await page.waitForSelector('.wl-item')
  mark('ready')
  await pause(page, 3)
  await click(page, page.locator('.wl-item').first())
  await page.waitForSelector('.gauge')
  await pause(page, 3)
  await page.mouse.move(700, 450, { steps: 20 })
  await pause(page, 3)
  await page.mouse.move(1300, 370, { steps: 20 })
  await pause(page, 4)
  await page.locator('.shelters').scrollIntoViewIfNeeded()
  await page.mouse.move(1350, 560, { steps: 20 })
  await pause(page, Math.max(4, durations.s3_hazard - 16))
})

// s4: the conversation and the draft.
await segment('s4_conversation', async (page, mark) => {
  await page.goto(`${BASE}/#/${RID}`)
  await page.waitForSelector('.gauge')
  mark('ready')
  await pause(page, 1)
  await click(page, page.getByRole('button', { name: 'Start the conversation' }))
  await pause(page, 1)
  await click(page, page.getByRole('button', { name: 'Use sample conversation' }))
  await pause(page, 3)
  await page.locator('#transcript').evaluate((el) => el.scrollTo({ top: 260, behavior: 'smooth' }))
  await pause(page, 2.5)
  await click(page, page.getByRole('button', { name: 'Draft plan' }))
  mark('draft_click')
  await page.waitForSelector('.form', { timeout: 180000 })
  mark('plan_shown')
  await pause(page, 2.5)
})

// s5: evidence chips, checks, a staff fix that clears a warning.
await segment('s5_plan', async (page, mark) => {
  await page.goto(`${BASE}/#/${RID}`)
  await page.waitForSelector('.form')
  mark('ready')
  await pause(page, 1.5)
  const chip = page.locator('#row-special_notes .ev', { hasText: /^F/ }).first()
  await click(page, chip)
  await pause(page, 3.5)
  await page.keyboard.press('Escape')
  await page.mouse.move(1380, 420, { steps: 20 })
  await pause(page, 3)
  await click(page, page.locator('#row-supporters button', { hasText: 'Edit' }))
  const phones = page.locator('#row-supporters input[aria-label="Phone"]')
  const n = await phones.count()
  for (let i = 0; i < n; i++) {
    if ((await phones.nth(i).inputValue()) === '') {
      await click(page, phones.nth(i))
      await phones.nth(i).pressSequentially('090-0000-3456', { delay: 60 })
      break
    }
  }
  await pause(page, 0.6)
  await click(page, page.locator('#row-supporters').getByRole('button', { name: 'Save change' }))
  mark('saved')
  await page.waitForSelector('#row-supporters .person', { timeout: 30000 })
  await page.mouse.move(1380, 330, { steps: 20 })
  await pause(page, Math.max(3, durations.s5_plan - 17))
})

// s6: copies and approval with the hanko seal.
await segment('s6_approval', async (page, mark) => {
  await page.goto(`${BASE}/#/${RID}`)
  await page.waitForSelector('.form')
  mark('ready')
  await click(page, page.getByRole('button', { name: 'Copies and approval' }))
  await click(page, page.getByRole('tab', { name: /Easy-read/ }))
  await click(page, page.getByRole('button', { name: 'Write the copies' }).first())
  mark('copies_click')
  await page.waitForSelector('.doc.md.easy h1, .doc.md.easy p', { timeout: 180000 })
  mark('copies_shown')
  await pause(page, 2.2)
  await click(page, page.getByRole('tab', { name: /Helper card/ }))
  await pause(page, 2)
  await click(page, page.getByRole('tab', { name: 'Official plan' }))
  await pause(page, 0.6)
  await click(page, page.getByRole('button', { name: 'Mark as reviewed with resident' }))
  await pause(page, 1.5)
  await click(page, page.getByRole('button', { name: 'Approve plan' }))
  await page.waitForSelector('.hanko')
  mark('stamped')
  await page.mouse.move(1100, 330, { steps: 10 })
  await pause(page, 6)
})

writeFileSync(`${OUT}marks.json`, JSON.stringify(marks, null, 1))
await browser.close()
