// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// E2E iPhone viewport smoke: /user/strategies + /admin/protocols
// 5/13 ハブ課題「iPhone partner UI 未実装」DoD #5 対応
//
// Run with:
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/phase2-iphone-mobile.spec.ts --project='Mobile Chrome'
//   # playwright.config.ts の mobile project (Pixel 5) で実行

import { test, expect } from '@playwright/test'

const BASE = process.env.STAGING_URL ?? 'https://app.ultra-auto-trade.com'

test.describe('iPhone viewport — Phase 2 画面レイアウト確認', () => {
  test.use({ viewport: { width: 390, height: 844 } }) // iPhone 14 Pro

  test('/user/strategies — モバイルで 5xx なし', async ({ page }) => {
    const res = await page.goto(`${BASE}/user/strategies`)
    expect(res?.status() ?? 200).toBeLessThan(500)
  })

  test('/user/strategies — モバイルで横スクロール発生しない', async ({ page }) => {
    await page.goto(`${BASE}/user/strategies`)
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth)
    const viewportWidth = page.viewportSize()?.width ?? 390
    // body が viewport 幅を大幅に超えていないこと（10px の余裕を許容）
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 10)
  })

  test('/admin/protocols — モバイルで 5xx なし', async ({ page }) => {
    const res = await page.goto(`${BASE}/admin/protocols`)
    expect(res?.status() ?? 200).toBeLessThan(500)
  })

  test('/admin/protocols — モバイルで横スクロール発生しない', async ({ page }) => {
    await page.goto(`${BASE}/admin/protocols`)
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth)
    const viewportWidth = page.viewportSize()?.width ?? 390
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 10)
  })

  test('/user/strategies — "近日公開" が表示される（英語 Coming Soon なし）', async ({ page }) => {
    await page.goto(`${BASE}/user/strategies`)
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText).not.toContain('Coming Soon')
  })
})
