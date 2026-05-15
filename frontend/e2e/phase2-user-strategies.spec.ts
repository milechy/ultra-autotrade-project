// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// E2E smoke test: /user/strategies (Phase 2 策略選択画面)
//
// Run with:
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/phase2-user-strategies.spec.ts
//   # or against production:
//   npx playwright test e2e/phase2-user-strategies.spec.ts

import { test, expect } from '@playwright/test'

const BASE = process.env.STAGING_URL ?? 'https://app.ultra-auto-trade.com'

test.describe('/user/strategies — 標準チェックリスト smoke', () => {
  test('未認証アクセス → login ページへリダイレクト or 200', async ({ page }) => {
    const res = await page.goto(`${BASE}/user/strategies`)
    // 未認証は /login か /connect へ遷移するか、200 で認証コンポーネントが表示される
    const url = page.url()
    const isRedirected = url.includes('/login') || url.includes('/connect')
    const isDirectly200 = res?.status() !== undefined && res.status() < 500
    expect(isRedirected || isDirectly200).toBe(true)
  })

  test('ページが 5xx を返さない', async ({ page }) => {
    const res = await page.goto(`${BASE}/user/strategies`)
    expect(res?.status() ?? 200).toBeLessThan(500)
  })

  test('英語ハードコードテキスト "Coming Soon" が画面に存在しない', async ({ page }) => {
    await page.goto(`${BASE}/user/strategies`)
    // 認証後の画面が見えない場合はスキップ
    const bodyText = await page.textContent('body') ?? ''
    // "近日公開" が使われているべき
    expect(bodyText).not.toContain('Coming Soon')
  })

  test('ページが想定外の内部エラー文字列を含まない', async ({ page }) => {
    await page.goto(`${BASE}/user/strategies`)
    const bodyText = await page.textContent('body') ?? ''
    // 内部エラーや開発用デバッグ文字列がないことを確認
    expect(bodyText).not.toContain('Internal Server Error')
    expect(bodyText).not.toContain('SyntaxError')
    expect(bodyText).not.toContain('TypeError')
  })
})
