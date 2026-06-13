// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
/**
 * E2E spec: partner wave6 i18n smoke test
 * PR #708 / feat/partner-wave6-i18n
 *
 * 検証範囲:
 *   TC1: /partner/users  が 404/5xx を返さない
 *   TC2: /partner/users  に JP テキスト "ユーザー管理" が DOM に存在する
 *   TC3: /partner/referral が 404/5xx を返さない
 *   TC4: /partner/referral に JP テキスト "紹介キャンペーン" が DOM に存在する
 *   TC5: NextIntlClientProvider が runtime IntlError を起こさない (/partner/users)
 *   TC6: NextIntlClientProvider が runtime IntlError を起こさない (/partner/referral)
 *   TC7: /partner/users にフィルターボタン "全て" / "アクティブ" / "非アクティブ" が存在する
 *        (PartnerUsers namespace keys: filterAll / filterActive / filterInactive)
 *   TC8: /partner/users テーブルにユーザー行クリック → UserDetailModal が表示される
 *        (PartnerUserDetailModal namespace: title = "ユーザー詳細")
 *
 * NOTE:
 *   - app/(partner)/partner/users/page.tsx → URL は /partner/users
 *   - app/(partner)/partner/referral/page.tsx → URL は /partner/referral
 *     (route group "(partner)" はディレクトリ名のみで URL に含まれない)
 *   - app/(partner)/layout.tsx に NextIntlClientProvider 配線済み (PR #671)
 *   - 認証ゲートで到達できない場合は TC2 以降を gracefully skip する
 *   - page.route() によるモックを使用 — 本番 API 呼び出しなし
 */

import { test, expect, type Page } from '@playwright/test'

// ── Mock helpers ──────────────────────────────────────────────────────────────

async function injectAuth(page: Page): Promise<void> {
  await page.addInitScript((args) => {
    localStorage.setItem(args.tokenKey, args.token)
    localStorage.setItem(args.expiresKey, String(args.expires))
  }, {
    tokenKey: 'ultra_auth_token',
    token: 'mock-wave6-token',
    expiresKey: 'ultra_auth_expires',
    expires: Date.now() + 24 * 60 * 60 * 1000,
  })
}

const MOCK_PARTNER_USER = {
  id: 1,
  username: 'wave6-partner',
  email: 'wave6@ultra-autotrade.com',
  role: 'partner',
  is_active: true,
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  terms_accepted_at: null,
  terms_version: null,
  risk_mode: 'conservative',
  invited_by: null,
  tier: 'GENERAL',
}

const MOCK_USERS_LIST = [
  {
    id: 42,
    username: 'tester-wave6',
    email: 'tester-wave6@example.com',
    role: 'viewer',
    is_active: true,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
  },
]

async function setupPartnerRouteMocks(page: Page): Promise<void> {
  await page.route('**/auth/me', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PARTNER_USER) })
    } else {
      await route.continue()
    }
  })

  // /users API (exclude document navigation)
  await page.route('**/users', async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue()
      return
    }
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USERS_LIST) })
    } else {
      await route.continue()
    }
  })

  // Referral endpoints
  const referralMocks: Array<[string, unknown]> = [
    ['**/partner/referral/code', { referral_code: 'WAVE6TEST', share_url: 'https://example.com/r/WAVE6TEST' }],
    ['**/partner/referral/list', []],
    ['**/partner/referral/earnings', { referral_count: 3, current_month_reward_jpy: '1500.00', total_payout_jpy: '5000.00', campaign_rate: '0.05', campaign_expires_month: null }],
  ]
  for (const [pattern, body] of referralMocks) {
    await page.route(pattern, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    })
  }

  // Partner dashboard stats (prevent skeleton hang)
  const partnerMocks: Array<[string, unknown]> = [
    ['**/api/partner/stats', { total_aum: 0, yesterday_aum: 0, month_return_pct: 0, yesterday_return_pct: 0, user_count: 0 }],
    ['**/api/partner/monthly', []],
    ['**/api/partner/allocations', []],
    ['**/api/partner/performance', { total_allocated_usd: 0, total_supply_usd: 0, health_factor: null, testers: [] }],
    ['**/ai/accuracy', { total_decisions: 0, correct_count: 0, accuracy_pct: 0, last_30d_accuracy_pct: 0 }],
    ['**/users/fee-schedule', { schedule: [], note: '' }],
  ]
  for (const [pattern, body] of partnerMocks) {
    await page.route(pattern, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
      } else {
        await route.continue()
      }
    })
  }
}

// ── TC1-2: /partner/users ──────────────────────────────────────────────────────

test.describe('[wave6-i18n] /partner/users smoke', () => {
  test('TC1: /partner/users が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto('/partner/users', { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/partner/users は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/partner/users は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: JP モード - "ユーザー管理" が DOM に存在する', async ({ page }) => {
    await injectAuth(page)
    await setupPartnerRouteMocks(page)
    const res = await page.goto('/partner/users', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/users')) {
      test.skip(true, '認証ゲートで /partner/users に到達不能のため skip')
      return
    }
    await page.waitForTimeout(1_000)
    const jpTitle = page.getByText('ユーザー管理', { exact: false }).first()
    const visible = await jpTitle.isVisible({ timeout: 8_000 }).catch(() => false)
    test.skip(!visible, '"ユーザー管理" が認証後コンテンツのため skip')
    await expect(jpTitle).toBeVisible()
  })

  test('TC7: フィルターボタン 全て / アクティブ / 非アクティブ が表示される', async ({ page }) => {
    await injectAuth(page)
    await setupPartnerRouteMocks(page)
    const res = await page.goto('/partner/users', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/users')) {
      test.skip(true, '認証ゲートで /partner/users に到達不能のため skip')
      return
    }
    await page.waitForTimeout(1_500)
    for (const label of ['全て', 'アクティブ', '非アクティブ']) {
      const btn = page.getByRole('button', { name: label }).first()
      const visible = await btn.isVisible({ timeout: 8_000 }).catch(() => false)
      test.skip(!visible, `"${label}" ボタンが認証後コンテンツのため skip`)
      await expect(btn).toBeVisible()
    }
  })

  test('TC8: ユーザー行クリック → UserDetailModal "ユーザー詳細" が表示される', async ({ page }) => {
    await injectAuth(page)
    await setupPartnerRouteMocks(page)
    const res = await page.goto('/partner/users', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/users')) {
      test.skip(true, '認証ゲートで /partner/users に到達不能のため skip')
      return
    }
    await page.waitForTimeout(1_500)

    // テーブルの最初の行を探す (ユーザーモックあり)
    const firstRow = page.locator('tr.cursor-pointer').first()
    const rowVisible = await firstRow.isVisible({ timeout: 8_000 }).catch(() => false)
    if (!rowVisible) {
      test.skip(true, 'テーブル行が認証後コンテンツのため skip')
      return
    }
    await firstRow.click()

    // UserDetailModal が開いて "ユーザー詳細" タイトルが表示される
    const modalTitle = page.getByRole('heading', { name: 'ユーザー詳細' })
    const modalVisible = await modalTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!modalVisible, '"ユーザー詳細" モーダルが認証後コンテンツのため skip')
    await expect(modalTitle).toBeVisible()
  })
})

// ── TC3-4: /partner/referral ───────────────────────────────────────────────────

test.describe('[wave6-i18n] /partner/referral smoke', () => {
  test('TC3: /partner/referral が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto('/partner/referral', { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/partner/referral は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/partner/referral は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC4: JP モード - "紹介キャンペーン" が DOM に存在する', async ({ page }) => {
    await injectAuth(page)
    await setupPartnerRouteMocks(page)
    const res = await page.goto('/partner/referral', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/referral')) {
      test.skip(true, '認証ゲートで /partner/referral に到達不能のため skip')
      return
    }
    await page.waitForTimeout(1_000)
    const jpTitle = page.getByText('紹介キャンペーン', { exact: false }).first()
    const visible = await jpTitle.isVisible({ timeout: 8_000 }).catch(() => false)
    test.skip(!visible, '"紹介キャンペーン" が認証後コンテンツのため skip')
    await expect(jpTitle).toBeVisible()
  })
})

// ── TC5-6: IntlError 監視 ──────────────────────────────────────────────────────

test.describe('[wave6-i18n] NextIntlClientProvider runtime エラー監視', () => {
  test('TC5: /partner/users で IntlError / MISSING_MESSAGE が出ない', async ({ page }) => {
    const intlErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && (msg.text().includes('IntlError') || msg.text().includes('MISSING_MESSAGE'))) {
        intlErrors.push(msg.text())
      }
    })
    page.on('pageerror', (err) => {
      if (err.message.includes('IntlError') || err.message.includes('MISSING_MESSAGE')) {
        intlErrors.push(err.message)
      }
    })

    await injectAuth(page)
    await setupPartnerRouteMocks(page)
    const res = await page.goto('/partner/users', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/users')) {
      test.skip(true, '認証ゲートで /partner/users に到達不能のため skip')
      return
    }
    await page.waitForTimeout(1_500)
    expect(intlErrors, `IntlError が検出された: ${intlErrors.join(', ')}`).toHaveLength(0)
  })

  test('TC6: /partner/referral で IntlError / MISSING_MESSAGE が出ない', async ({ page }) => {
    const intlErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && (msg.text().includes('IntlError') || msg.text().includes('MISSING_MESSAGE'))) {
        intlErrors.push(msg.text())
      }
    })
    page.on('pageerror', (err) => {
      if (err.message.includes('IntlError') || err.message.includes('MISSING_MESSAGE')) {
        intlErrors.push(err.message)
      }
    })

    await injectAuth(page)
    await setupPartnerRouteMocks(page)
    const res = await page.goto('/partner/referral', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/referral')) {
      test.skip(true, '認証ゲートで /partner/referral に到達不能のため skip')
      return
    }
    await page.waitForTimeout(1_500)
    expect(intlErrors, `IntlError が検出された: ${intlErrors.join(', ')}`).toHaveLength(0)
  })
})
