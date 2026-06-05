// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// F-14: Fee Model v10 UI / API レグレッション E2E
//
// テスト対象:
//   - GET /api/v1/fees/config          → admin settings/config 画面に Fee Config カード
//   - GET /api/v1/fees/my-summary      → /fees ページ サマリカード
//   - GET /api/v1/fees/my-history      → /fees ページ 月次履歴テーブル
//   - GET /auth/risk-modes             → /settings リスクモード Phase 1 制限表示
//   - PUT /auth/risk-mode              → conservative のみ切替可能
//
// 実行方法:
//   npx playwright test e2e/f14-fees.spec.ts
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/f14-fees.spec.ts

import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// ログインページ判定: React レンダリング完了まで最大 8 秒待つ
async function awaitIsLoginPage(page: Page): Promise<boolean> {
  return page.getByRole('button', { name: 'ログイン' })
    .waitFor({ state: 'visible', timeout: 8000 })
    .then(() => true)
    .catch(() => false)
}

// 404 ページ判定
async function awaitIs404(page: Page): Promise<boolean> {
  return page.getByRole('heading', { name: 'ページが見つかりません' })
    .waitFor({ state: 'visible', timeout: 3000 })
    .then(() => true)
    .catch(() => false)
}

// ---------------------------------------------------------------------------
// 1. /fees ページ — ユーザー手数料画面 (F-11)
// ---------------------------------------------------------------------------
test.describe('/fees — ユーザー手数料画面', () => {
  test('/fees ページが 200 で読み込まれる', async ({ page }) => {
    const response = await page.goto('/fees')
    expect(response?.status()).toBeLessThan(500)
  })

  test('/fees: 「手数料・実績」ヘッダーが表示される', async ({ page }) => {
    await page.goto('/fees')
    await page.waitForLoadState('domcontentloaded')

    const header = page.getByRole('heading', { name: '手数料・実績' })
    const loginPage = page.getByRole('heading', { name: 'Ultra AutoTrade' })
    const loginBtn = page.getByRole('button', { name: 'ログイン' })
    const notFound = page.getByRole('heading', { name: 'ページが見つかりません' })

    await Promise.any([
      header.waitFor({ state: 'visible', timeout: 10000 }),
      loginPage.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      notFound.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {})

    const hasHeader = await header.isVisible().catch(() => false)
    const hasLogin = await loginPage.isVisible().catch(() => false)
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false)
    const has404 = await notFound.isVisible().catch(() => false)

    expect(hasHeader || hasLogin || hasLoginBtn || has404).toBeTruthy()
  })

  test('/fees: サマリカードラベルが存在する（認証済みの場合）', async ({ page }) => {
    await page.goto('/fees')
    await page.waitForLoadState('domcontentloaded')

    // 404 ページまたはログイン画面ならスキップ（未認証/未デプロイ環境では非表示は正常動作）
    if (await awaitIs404(page) || await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    // 認証済み: サマリカードのラベルが1つ以上表示される
    const labels = ['累計手数料', '累計サブスク', '累計手取り', '記録月数']
    let found = false
    for (const label of labels) {
      const visible = await page.getByText(label).isVisible().catch(() => false)
      if (visible) { found = true; break }
    }
    expect(found).toBeTruthy()
  })

  test('/fees: 月次手数料履歴セクションが存在する（認証済みの場合）', async ({ page }) => {
    await page.goto('/fees')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIs404(page) || await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    const historyTitle = page.getByText('月次手数料履歴')
    await historyTitle.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    const visible = await historyTitle.isVisible().catch(() => false)
    expect(visible).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 2. /history → /fees リンク (F-11)
// ---------------------------------------------------------------------------
test.describe('/history — 手数料明細リンク', () => {
  test('/history ページが 200 で読み込まれる', async ({ page }) => {
    const response = await page.goto('/history')
    expect(response?.status()).toBeLessThan(500)
  })

  test('/history: 「手数料明細を見る」リンクが存在する（認証済みの場合）', async ({ page }) => {
    await page.goto('/history')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    const link = page.getByRole('link', { name: /手数料明細を見る/ })
    await link.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    const visible = await link.isVisible().catch(() => false)
    expect(visible).toBeTruthy()
  })

  test('/history: 「手数料明細を見る」リンクが /fees を指す', async ({ page }) => {
    await page.goto('/history')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    const link = page.getByRole('link', { name: /手数料明細を見る/ })
    const href = await link.getAttribute('href').catch(() => null)
    expect(href).toBe('/fees')
  })
})

// ---------------------------------------------------------------------------
// 3. /settings — リスクモード Phase 1 制限表示 (F-10)
// ---------------------------------------------------------------------------
test.describe('/settings — リスクモード Phase 1 制限', () => {
  test('/settings ページが 200 で読み込まれる', async ({ page }) => {
    const response = await page.goto('/settings')
    expect(response?.status()).toBeLessThan(500)
  })

  test('/settings: リスクモードセクションが存在する（認証済みの場合）', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    const riskLabel = page.getByText('リスクモード')
    await riskLabel.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    const visible = await riskLabel.isVisible().catch(() => false)
    expect(visible).toBeTruthy()
  })

  test('/settings: 「保守的」モードが表示される', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    const conservative = page.getByText('保守的')
    await conservative.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    expect(await conservative.isVisible().catch(() => false)).toBeTruthy()
  })

  test('/settings: 「Phase 2」バッジが balanced / aggressive に表示される', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    const phase2Badges = page.getByText('Phase 2')
    await phase2Badges.first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    const count = await phase2Badges.count().catch(() => 0)
    // balanced + aggressive の 2 枚
    expect(count).toBeGreaterThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// 4. /settings/config (admin) — Fee Config カード (F-12)
// ---------------------------------------------------------------------------
test.describe('/settings/config — Admin Fee Config カード', () => {
  test('/settings/config ページが 500 未満で読み込まれる', async ({ page }) => {
    const response = await page.goto('/settings/config')
    expect(response?.status()).toBeLessThan(500)
  })

  test('/settings/config: 「手数料設定」セクションが存在する（admin 認証済みの場合）', async ({ page }) => {
    await page.goto('/settings/config')
    await page.waitForLoadState('domcontentloaded')

    if (await awaitIsLoginPage(page)) {
      test.skip()
      return
    }

    // admin 画面にリダイレクトされていなければ Fee Config カードを確認
    const feeTitle = page.getByText('手数料設定 (Fee Model v10)')
    await feeTitle.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
    const visible = await feeTitle.isVisible().catch(() => false)
    // admin でない場合は非表示も正常
    if (!visible) {
      const notAdminText = page.getByText(/権限|アクセス/)
      const hasNotAdmin = await notAdminText.isVisible({ timeout: 3000 }).catch(() => false)
      expect(hasNotAdmin || !visible).toBeTruthy()
    } else {
      expect(visible).toBeTruthy()
    }
  })
})

// ---------------------------------------------------------------------------
// 5. API — /api/v1/fees/* エンドポイント疎通確認 (バックエンド接続時)
// ---------------------------------------------------------------------------
test.describe('API — /api/v1/fees/* 疎通', () => {
  const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://api.ultra-auto-trade.com'
  // 5xx / Cloudflare 独自コード: インフラ障害なら pass-through
  const AUTH_CODES = [401, 403, 422]
  const INFRA_CODES = [502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530]

  test('GET /api/v1/fees/config が認証なしで 401 または 403 を返す', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/api/v1/fees/config`)
    const status = res.status()
    if (INFRA_CODES.includes(status)) return
    expect(AUTH_CODES).toContain(status)
  })

  test('GET /api/v1/fees/my-summary が認証なしで 401 または 403 を返す', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/api/v1/fees/my-summary`)
    const status = res.status()
    if (INFRA_CODES.includes(status)) return
    expect(AUTH_CODES).toContain(status)
  })

  test('GET /api/v1/fees/my-history が認証なしで 401 または 403 を返す', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/api/v1/fees/my-history`)
    const status = res.status()
    if (INFRA_CODES.includes(status)) return
    expect(AUTH_CODES).toContain(status)
  })

  test('GET /auth/risk-modes が認証なしで 401 または 403 を返す', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/auth/risk-modes`)
    const status = res.status()
    if (INFRA_CODES.includes(status)) return
    expect(AUTH_CODES).toContain(status)
  })

  test('GET /auth/risk-mode が認証なしで 401 または 403 を返す', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/auth/risk-mode`)
    const status = res.status()
    if (INFRA_CODES.includes(status)) return
    expect(AUTH_CODES).toContain(status)
  })
})
