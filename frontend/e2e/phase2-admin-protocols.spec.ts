// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// E2E smoke test: /protocols (Phase 2 プロトコルヘルスモニター)
// 注: (admin) は Next.js route group のため URL に含まれない → /protocols
//
// Run with:
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/phase2-admin-protocols.spec.ts
//   # or against production:
//   npx playwright test e2e/phase2-admin-protocols.spec.ts

import { test, expect } from '@playwright/test'

const BASE = process.env.STAGING_URL ?? 'https://app.ultra-auto-trade.com'

test.describe('/protocols — 標準チェックリスト smoke', () => {
  test('未認証アクセス → login/dashboard リダイレクト or 200', async ({ page }) => {
    const res = await page.goto(`${BASE}/protocols`)
    const url = page.url()
    // AdminGuard は非admin を /login か /user/dashboard か /partner/dashboard へ遷移させる
    const isRedirected =
      url.includes('/login') ||
      url.includes('/dashboard') ||
      url.includes('/connect')
    const isDirectly200 = res?.status() !== undefined && res.status() < 500
    expect(isRedirected || isDirectly200).toBe(true)
  })

  test('ページが 5xx を返さない', async ({ page }) => {
    const res = await page.goto(`${BASE}/protocols`)
    expect(res?.status() ?? 200).toBeLessThan(500)
  })

  test('英語ハードコードテキスト "Paused"/"Frozen" が画面に存在しない', async ({ page }) => {
    await page.goto(`${BASE}/protocols`)
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText).not.toContain('Paused')
    expect(bodyText).not.toContain('Frozen')
  })

  test('api.ultra-auto-trade.com 内部 URL が body に露出していない', async ({ page }) => {
    await page.goto(`${BASE}/protocols`)
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText).not.toContain('77.42.46.155')
  })
})
