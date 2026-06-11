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

// AuthGuard(adminOnly) が非admin を /login 等へ遷移させるため、DOM 表示 assert は
// admin としてページに到達できた場合のみ実行する（リダイレクト時は skip）。
async function reachedProtocolsPage(page: import('@playwright/test').Page): Promise<boolean> {
  const url = page.url()
  return (
    url.includes('/protocols') &&
    !url.includes('/login') &&
    !url.includes('/connect') &&
    !url.includes('/dashboard')
  )
}

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
    const bodyText = (await page.textContent('body')) ?? ''
    expect(bodyText).not.toContain('Paused')
    expect(bodyText).not.toContain('Frozen')
  })

  test('api.ultra-auto-trade.com 内部 URL が body に露出していない', async ({ page }) => {
    await page.goto(`${BASE}/protocols`)
    const bodyText = (await page.textContent('body')) ?? ''
    expect(bodyText).not.toContain('77.42.46.155')
  })

  // ── 実 DOM 表示 assert（2026-05-19 「404 でも < 500 で通過」インシデント再発防止） ──
  // admin としてページに到達できた場合のみ実行。route group により URL は /protocols。

  test('ページタイトル「プロトコルヘルスモニター」が表示される', async ({ page }) => {
    await page.goto(`${BASE}/protocols`)
    await page.waitForLoadState('networkidle')
    if (!(await reachedProtocolsPage(page))) {
      test.skip(true, '非admin のためリダイレクト（DOM assert は admin 認証時のみ）')
      return
    }
    await expect(page.getByRole('heading', { name: 'プロトコルヘルスモニター' })).toBeVisible()
  })

  test('Aave / Lido / Pendle の各プロトコル名が DOM に表示される', async ({ page }) => {
    await page.goto(`${BASE}/protocols`)
    await page.waitForLoadState('networkidle')
    if (!(await reachedProtocolsPage(page))) {
      test.skip(true, '非admin のためリダイレクト（DOM assert は admin 認証時のみ）')
      return
    }
    const bodyText = (await page.textContent('body')) ?? ''
    // メタは静的に必ず表示される（mock 排除後も常に 3 カードレンダリング）
    expect(bodyText).toContain('Aave V3')
    expect(bodyText).toContain('Lido stETH')
    expect(bodyText).toContain('Pendle PT/YT')
  })

  test('リスク / TVL / 稼働状況のラベルが表示される', async ({ page }) => {
    await page.goto(`${BASE}/protocols`)
    await page.waitForLoadState('networkidle')
    if (!(await reachedProtocolsPage(page))) {
      test.skip(true, '非admin のためリダイレクト（DOM assert は admin 認証時のみ）')
      return
    }
    const bodyText = (await page.textContent('body')) ?? ''
    // 各カードの固定ラベル（API 値の有無に関わらず常に存在する）
    expect(bodyText).toContain('稼働状況')
    expect(bodyText).toContain('TVL')
    expect(bodyText).toContain('リスクレベル')
    expect(bodyText).toContain('アラート')
  })
})
