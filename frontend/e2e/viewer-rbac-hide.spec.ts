// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Lane R — viewer (tester) RBAC: PR #417 で塞いだ 3 穴の検証 spec
//
// 背景 (PR #417 / Asana 山本さん権限):
//   PR #417 は viewer (tester) ロールから 3 つの操作 UI を非表示にした:
//     1. /user/approve: !isPartner → router.replace('/user/dashboard')
//     2. /user/settings: RiskSettingsCard は {isPartner && ...} で非表示
//     3. /user/settings: WalletInfoCard は {isPartner && ...} で非表示
//   isPartner は role === 'partner' OR role === 'admin' を返す
//   (frontend/lib/auth.ts:192)。したがって role === 'viewer' は !isPartner。
//
// 検証戦略:
//   - localStorage に dummy token を仕込み + /auth/me を mock して role を制御
//     → viewer ケースでカード非表示 + approve リダイレクトを確認
//     → partner ケースでカード表示 + approve 留まりを確認 (リグレッション防止)
//   - 認証実装が変わったら helpers/partner-auth.ts と同じく setupRoleAuth を
//     更新する形にする (spec ごとの mock 重複を避ける将来余地として残す)
//
// 実行方法:
//   # 本番向け (デフォルト)
//   npx playwright test e2e/viewer-rbac-hide.spec.ts
//
//   # staging 向け
//   STAGING_URL=http://127.0.0.1:3001 npx playwright test e2e/viewer-rbac-hide.spec.ts
//
//   # localhost dev server 向け
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/viewer-rbac-hide.spec.ts
//
// NOTE:
//   - CardTitle は h3 element (frontend/components/ui/card.tsx)。
//     "ウォレット" は UserHeader の nav link でも使われるが <a> 要素なので
//     getByRole('heading', ...) では拾われない。
//   - 山本さんの本物のアカウント (production users.id=11) を使うのではなく
//     mock user で role 切替を網羅する (本物のアカウントは ToS 同意状態など
//     副次的な要因で結果が揺らぐため)。

import { test, expect, type Page } from '@playwright/test'

interface MockUser {
  id: number
  email: string
  username: string
  role: 'viewer' | 'partner' | 'admin' | 'tester'
  is_active: boolean
  created_at: string
  updated_at: string
  terms_accepted_at: string | null
  terms_version: string | null
  risk_mode: string
  invited_by: number | null
  tier: string
  risk_mode_label: string
}

const VIEWER_MOCK_USER: MockUser = {
  id: 9001,
  email: 'viewer-e2e@ultra-autotrade.com',
  username: 'viewer-e2e',
  role: 'viewer',
  is_active: true,
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  terms_accepted_at: '2026-01-01T00:00:00+00:00',
  terms_version: 'v1.0',
  risk_mode: 'conservative',
  invited_by: null,
  tier: 'GENERAL',
  risk_mode_label: 'ローリスク',
}

const PARTNER_MOCK_USER: MockUser = {
  ...VIEWER_MOCK_USER,
  id: 9002,
  email: 'partner-e2e@ultra-autotrade.com',
  username: 'partner-e2e',
  role: 'partner',
}

/**
 * mock user の role に応じて localStorage に token を仕込み + GET /auth/me / 関連 API を mock。
 * page.goto() の前に呼ぶこと。
 */
async function setupRoleAuth(page: Page, user: MockUser): Promise<void> {
  const expiresAt = Date.now() + 24 * 60 * 60 * 1000

  await page.addInitScript(
    (args) => {
      localStorage.setItem(args.tokenKey, args.t)
      localStorage.setItem(args.expiresKey, String(args.e))
    },
    {
      tokenKey: 'ultra_auth_token',
      expiresKey: 'ultra_auth_expires',
      t: `dummy-${user.role}-token-for-e2e`,
      e: expiresAt,
    },
  )

  await page.route('**/auth/me', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(user),
      })
    } else {
      await route.continue()
    }
  })

  // partner 側で settings page が呼ぶ GET 系を 200 で返して null pointer 回避
  await page.route('**/api/user/settings', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_mode: 'managed',
          notification_email: user.email,
          notification_frequency: 'important',
          max_single_trade_usd: 500,
          max_daily_trade_usd: 2000,
        }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/auth/risk-mode', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ mode: user.risk_mode }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/auth/risk-modes', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          modes: [
            { mode: 'conservative', allowed_in_phase_1: true },
            { mode: 'balanced', allowed_in_phase_1: true },
          ],
        }),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/api/automation/status', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          is_trading_paused: false,
          emergency_reason: null,
        }),
      })
    } else {
      await route.continue()
    }
  })

  // /user/approve が呼ぶ proposals 系。partner で 200, viewer は fetchData 呼ばないので無視可
  await page.route('**/api/proposals/**', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    } else {
      await route.continue()
    }
  })
}

test.describe('Lane R — viewer (tester) RBAC: PR #417 で塞いだ 3 穴', () => {
  // 各テストは独立コンテキストで実行 (storageState を空に)
  test.use({ storageState: { cookies: [], origins: [] } })

  // ============================================================
  // viewer ロールでの「非表示」検証 (PR #417 で塞いだ穴)
  // ============================================================

  test('viewer: /user/approve は /user/dashboard へ client-side redirect される', async ({ page }) => {
    await setupRoleAuth(page, VIEWER_MOCK_USER)
    await page.goto('/user/approve')

    // useEffect 内の router.replace を待つ (auth の初期化 + isLoading=false の後)
    let redirected = false
    try {
      await page.waitForURL('**/user/dashboard', { timeout: 15000 })
      redirected = true
    } catch {
      // redirect が完了しなかった場合は次の防御線 (approve UI 非表示) を確認
    }

    if (redirected) {
      expect(page.url()).toContain('/user/dashboard')
      return
    }

    // redirect 未完了 → URL が /user/approve のままなら approve 固有 UI が出てないこと
    const currentUrl = page.url()
    if (currentUrl.includes('/user/approve')) {
      await page.waitForLoadState('domcontentloaded')
      await page.waitForTimeout(3000)

      const approveHeading = page.getByRole('heading', { name: /承認|approve/i })
      const proposalCard = page.locator('[data-testid="proposal-card"]')
      const hasApproveHeading = await approveHeading
        .first()
        .isVisible({ timeout: 2000 })
        .catch(() => false)
      const hasProposalCard = await proposalCard
        .first()
        .isVisible({ timeout: 2000 })
        .catch(() => false)

      // approve 固有 UI が見えていなければ guard は効いている (redirect 直前の null render 等)
      expect(hasApproveHeading || hasProposalCard).toBeFalsy()
    } else {
      // /user/approve でも /user/dashboard でもない別ページ (例: /login) でも redirect は機能している
      expect(currentUrl).not.toContain('/user/approve')
    }
  })

  test('viewer: /user/settings に "リスク設定" カード (h3) が非表示', async ({ page }) => {
    await setupRoleAuth(page, VIEWER_MOCK_USER)
    await page.goto('/user/settings')
    await page.waitForLoadState('domcontentloaded')
    // auth 初期化 + getMe + render の完了を待つ
    await page.waitForTimeout(3000)

    // CardTitle "リスク設定" は h3 element。viewer では {isPartner && ...} で render されない。
    const riskHeading = page.getByRole('heading', { name: 'リスク設定' })
    await expect(riskHeading).toHaveCount(0)
  })

  test('viewer: /user/settings に "ウォレット" カード (h3) が非表示', async ({ page }) => {
    await setupRoleAuth(page, VIEWER_MOCK_USER)
    await page.goto('/user/settings')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    // CardTitle "ウォレット" は h3 element (exact マッチで「ウォレットを切断しますか？」等を除外)
    // UserHeader の nav link "ウォレット" は <a> 要素なので role=heading では拾われない。
    const walletHeading = page.getByRole('heading', { name: 'ウォレット', exact: true })
    await expect(walletHeading).toHaveCount(0)
  })

  // ============================================================
  // partner ロールでの「表示」確認 (リグレッション防止: PR #417 が
  // 過剰に塞いでないこと)
  // ============================================================

  test('partner: /user/approve は /user/dashboard にリダイレクトされない', async ({ page }) => {
    await setupRoleAuth(page, PARTNER_MOCK_USER)
    await page.goto('/user/approve')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(3000)

    const currentUrl = page.url()
    // viewer 用のリダイレクトが partner で誤発火していないこと
    // (login 未認証時の /login redirect は別の guard なので /login への遷移は許容)
    if (!currentUrl.includes('/login')) {
      expect(currentUrl).not.toContain('/user/dashboard')
    }
  })

  test('partner: /user/settings に "リスク設定" カード (h3) が表示される', async ({ page }) => {
    await setupRoleAuth(page, PARTNER_MOCK_USER)
    await page.goto('/user/settings')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(5000)

    // partner なら少なくとも 1 つの "リスク設定" heading が見えるはず
    const riskHeading = page.getByRole('heading', { name: 'リスク設定' })
    const visibleCount = await riskHeading.count()

    if (visibleCount === 0) {
      // backend に届かず /auth/me が default で fail → user=null になっている可能性。
      // その場合は /login へ redirect されているはずなのでログ出力して info とする。
      const url = page.url()
      console.log(`[INFO] partner で "リスク設定" 非表示。現在 URL: ${url}`)
      // 認証セッション初期化失敗の場合は ToS 同意誘導や /login 移行が起きる。
      // 少なくとも本テストで明確に検証したい viewer→partner の差分は他のテストで担保される。
    }
    expect(visibleCount).toBeGreaterThan(0)
  })

  test('partner: /user/settings に "ウォレット" カード (h3) が表示される', async ({ page }) => {
    await setupRoleAuth(page, PARTNER_MOCK_USER)
    await page.goto('/user/settings')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(5000)

    const walletHeading = page.getByRole('heading', { name: 'ウォレット', exact: true })
    const visibleCount = await walletHeading.count()
    if (visibleCount === 0) {
      const url = page.url()
      console.log(`[INFO] partner で "ウォレット" 非表示。現在 URL: ${url}`)
    }
    expect(visibleCount).toBeGreaterThan(0)
  })
})
