// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Lane F-2: /partner/users/[id] 詳細ページ + /partner/referral/[id] KPI セクション
// DOM 制約: wallet_address / tx_hash を一切 render しないことを自動検証する
//
// 実行方法:
//   npx playwright test e2e/partner-users-detail.spec.ts
//   (credentials 不要 — すべて page.route() でモック)

import { test, expect, type Page } from '@playwright/test'
import path from 'path'
import fs from 'fs'

// ── Mock data ──────────────────────────────────────────────────────────────────

const PARTNER_MOCK_USER = {
  id: 1,
  username: 'partner-f2-test',
  email: 'partner-f2@ultra-autotrade.com',
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

const MOCK_USER_STATS = {
  user_id: 1,
  today_amount: '5000.00',
  month_amount: '4800.00',
  yesterday_return_pct: '0.51',
  month_return_pct: '2.10',
}

const MOCK_AI_DECISIONS = {
  items: [
    {
      id: 1,
      user_id: null,
      query: 'BTC/USD market analysis',
      action: 'HOLD',
      confidence: 72,
      reason: 'Market uncertainty',
      primary_provider: 'claude',
      primary_action: 'HOLD',
      primary_confidence: 72,
      secondary_provider: null,
      secondary_action: null,
      secondary_confidence: null,
      agreed: true,
      rag_context_json: null,
      created_at: '2026-05-11T10:00:00+00:00',
    },
  ],
  total: 1,
  limit: 5,
  offset: 0,
}

const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'partner-users-detail')
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
}

// ── Setup helper ───────────────────────────────────────────────────────────────

async function setupPartnerMocks(page: Page): Promise<void> {
  // Inject auth state (token + expiry)
  await page.addInitScript((args) => {
    localStorage.setItem(args.tokenKey, args.token)
    localStorage.setItem(args.expiresKey, String(args.expires))
  }, {
    tokenKey: 'ultra_auth_token',
    token: 'mock-f2-test-token',
    expiresKey: 'ultra_auth_expires',
    expires: Date.now() + 24 * 60 * 60 * 1000,
  })

  // Mock /auth/me
  await page.route('**/auth/me', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(PARTNER_MOCK_USER),
      })
    } else {
      await route.continue()
    }
  })

  // Mock partner user stats
  await page.route('**/api/partner/users/*/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_USER_STATS),
    })
  })

  // Mock AI decisions
  await page.route('**/api/ai/decisions*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_AI_DECISIONS),
    })
  })

  // Mock referral transactions (used by /partner/referral/[id])
  await page.route('**/partner/referral/users/*/transactions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  // Common mocks to prevent Skeleton hang
  const commonMocks: Array<[string, unknown]> = [
    ['**/api/partner/stats', { total_aum: 0, yesterday_aum: 0, month_return_pct: 0, yesterday_return_pct: 0, user_count: 0 }],
    ['**/api/partner/monthly', []],
    ['**/api/partner/allocations', []],
    ['**/api/partner/performance', { total_allocated_usd: 0, total_supply_usd: 0, health_factor: null, testers: [] }],
    ['**/ai/accuracy', { total_decisions: 0, correct_count: 0, accuracy_pct: 0, last_30d_accuracy_pct: 0 }],
    ['**/users/fee-schedule', { schedule: [], note: '' }],
    ['**/partner/referral/code', { referral_code: 'TEST123', share_url: 'https://example.com/r/TEST123' }],
    ['**/partner/referral/list', []],
  ]
  for (const [pattern, body] of commonMocks) {
    await page.route(pattern, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(body),
        })
      } else {
        await route.continue()
      }
    })
  }

  // /users は document ナビゲーション (/partner/users) を除外して API のみモック
  await page.route('**/users', async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue()
      return
    }
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    } else {
      await route.continue()
    }
  })
}

// ── TC-F2-1: /partner/users/1 KPI カード表示 ──────────────────────────────────

test.describe('TC-F2-1: /partner/users/[id] 詳細ページ', () => {
  test('KPI カード 3 枚が表示される', async ({ page }) => {
    await setupPartnerMocks(page)
    await page.goto('/partner/users/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    // ページが /login にリダイレクトされていないこと
    expect(page.url()).toContain('/partner/users/1')

    // 「テスター詳細」見出し
    await expect(page.getByRole('heading', { name: 'テスター詳細' })).toBeVisible({ timeout: 10_000 })

    // KPI ラベルが 3 枚分表示される
    const kpiLabels = ['今日の運用残高', '今月の利回り', '昨日の利回り']
    for (const label of kpiLabels) {
      await expect(page.getByText(label).first()).toBeVisible({ timeout: 10_000 })
    }

    // 「テスター一覧に戻る」リンク
    await expect(page.getByText('テスター一覧に戻る')).toBeVisible()

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'tc-f2-1-user-detail-kpi.png'), fullPage: true })
  })

  test('AI 判定セクションが表示される', async ({ page }) => {
    await setupPartnerMocks(page)
    await page.goto('/partner/users/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    // AI 判定テーブルヘッダー
    await expect(page.getByText('AI 判定履歴').first()).toBeVisible({ timeout: 10_000 })

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'tc-f2-1-user-detail-ai.png'), fullPage: true })
  })
})

// ── TC-F2-2: DOM に wallet_address / tx_hash が存在しない ─────────────────────

test.describe('TC-F2-2: DOM 制約 — wallet_address / tx_hash 非表示', () => {
  test('/partner/users/1 に wallet_address が render されない', async ({ page }) => {
    await setupPartnerMocks(page)
    await page.goto('/partner/users/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    const bodyText = await page.evaluate(() => document.body.innerText)
    expect(bodyText).not.toContain('wallet_address')
    expect(bodyText).not.toContain('tx_hash')
    // 0x... アドレス形式も含まれないこと
    expect(bodyText).not.toMatch(/0x[0-9a-fA-F]{10,}/)
  })

  test('/partner/referral/1 に wallet_address が render されない', async ({ page }) => {
    await setupPartnerMocks(page)
    await page.goto('/partner/referral/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    const bodyText = await page.evaluate(() => document.body.innerText)
    expect(bodyText).not.toContain('wallet_address')
    expect(bodyText).not.toContain('tx_hash')
  })
})

// ── TC-F2-3: /partner/referral/[id] KPI セクション ────────────────────────────

test.describe('TC-F2-3: /partner/referral/[id] 運用状況 KPI', () => {
  test('KPI セクション（今日の運用残高 / 今月の利回り）が表示される', async ({ page }) => {
    await setupPartnerMocks(page)
    await page.goto('/partner/referral/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    expect(page.url()).toContain('/partner/referral/1')

    // KPI ラベル
    await expect(page.getByText('今日の運用残高').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('今月の利回り').first()).toBeVisible({ timeout: 10_000 })

    // 「紹介一覧に戻る」リンク
    await expect(page.getByText('紹介一覧に戻る')).toBeVisible()

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'tc-f2-3-referral-detail-kpi.png'), fullPage: true })
  })
})

// ── TC-F2-4: /partner/users から詳細リンク ────────────────────────────────────

test.describe('TC-F2-4: /partner/users 一覧の詳細リンク', () => {
  test('テーブルに「詳細」リンクが含まれる（ユーザーありのとき）', async ({ page }) => {
    await setupPartnerMocks(page)

    // setupPartnerMocks の /users モック（空配列）を 1 ユーザーで上書き (last-wins)
    // resourceType チェックでページナビゲーションを除外
    await page.route('**/users', async (route) => {
      if (route.request().resourceType() === 'document') {
        await route.continue()
        return
      }
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 42,
              username: 'tester-a',
              email: 'tester-a@example.com',
              role: 'viewer',
              is_active: true,
              created_at: '2026-01-01T00:00:00+00:00',
              updated_at: '2026-01-01T00:00:00+00:00',
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/users')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    // 詳細リンクが存在すること
    const detailLink = page.getByRole('link', { name: '詳細' }).first()
    await expect(detailLink).toBeVisible({ timeout: 10_000 })

    const href = await detailLink.getAttribute('href')
    expect(href).toMatch(/\/partner\/users\/\d+/)

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'tc-f2-4-users-list-detail-link.png'), fullPage: true })
  })
})
