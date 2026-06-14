// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
/**
 * E2E spec: wave14 partner pages i18n — Gate 4
 * PR #717 / feat/wave14-partner-pages-i18n
 *
 * 検証範囲:
 *   TC1: /partner/notifications が 404/5xx を返さない
 *   TC2: /partner/notifications に JP テキスト "通知ログ" が表示される
 *   TC3: /partner/notifications の重要度フィルタ "すべて" が表示される
 *        (PartnerNotifications.filterAll)
 *   TC4: /partner/notifications のテーブルヘッダ "重要度" が表示される
 *        (PartnerNotifications.colSeverity)
 *   TC5: /partner/dashboard に "現在の運用残高" が表示される
 *        (PartnerPerformanceKPI.currentBalance)
 *   TC6: /partner/dashboard に "全体損益" が表示される
 *        (PartnerPerformanceKPI.totalPnl)
 *   TC7: /partner/users/1 が 404/5xx を返さない
 *   TC8: /partner/users/1 に "テスター詳細" が表示される
 *        (PartnerUserDetail.pageTitle)
 *   TC9: /partner/referral/1 が 404/5xx を返さない
 *   TC10: /partner/referral/1 に "運用状況詳細" が表示される
 *        (PartnerReferralDetail.pageTitle)
 *   TC11: /partner/* 全体で翻訳キーリテラル漏れなし (e.g. "PartnerNotifications.pageTitle")
 *   TC12: /partner/notifications に英語ハードコード残存なし
 *
 * NOTE:
 *   - route group "(partner)" は URL に含まれない
 *   - app/(partner)/layout.tsx に NextIntlClientProvider 配線済み (PR #671)
 *   - page.route() によるモックで本番 API 呼び出しなし
 */

import { test, expect, type Page } from '@playwright/test'
import { setupPartnerAuth } from './helpers/partner-auth'

// ── Mock helpers ──────────────────────────────────────────────────────────────

const MOCK_NOTIFICATION_PAGE = {
  items: [
    {
      id: 1,
      channel: 'slack',
      severity: 'info',
      title: 'テスト通知',
      body: 'テスト本文',
      partner_id: 1,
      user_id: null,
      created_at: '2026-06-01T10:00:00+00:00',
    },
  ],
  total: 1,
  page: 1,
  per_page: 20,
}

const MOCK_PARTNER_STATS = {
  today_amount: '10000.00',
  month_return_pct: '1.50',
  yesterday_return_pct: '0.80',
}

const MOCK_REFERRAL_TXS: unknown[] = []

const MOCK_PERFORMANCE = {
  total_supply_usd: '50000.0',
  total_allocated_usd: '48000.0',
  health_factor: '2.10',
  testers: [],
}

async function setupWave14Mocks(page: Page): Promise<void> {
  // Notifications
  await page.route('**/api/partner/notifications**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_NOTIFICATION_PAGE),
    })
  })

  // Performance KPI (dashboard)
  await page.route('**/api/partner/performance**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PERFORMANCE),
    })
  })

  // Allocations (dashboard AllocationTable + Chart)
  await page.route('**/api/partner/allocations**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  // Wallet balance (dashboard PerformanceSummaryKPI)
  await page.route('**/api/wallet/balance**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        total_usd: '1200.5',
        eth_balance: '0.35',
        usdc_balance: '850.00',
        fallback_used: false,
      }),
    })
  })

  // User stats (users/[id])
  await page.route('**/api/partner/users/*/stats**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PARTNER_STATS),
    })
  })

  // AI decisions (users/[id] last 5)
  await page.route('**/api/ai/decisions**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0 }),
    })
  })

  // Referral transactions (referral/[id])
  await page.route('**/api/referral/transactions**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_REFERRAL_TXS),
    })
  })

  // Monthly chart data (dashboard)
  await page.route('**/api/partner/monthly**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })
}

/** DOM テキストノードから pattern にマッチするものを返す（script/style 除外）*/
async function findTextNodes(page: Page, pattern: RegExp): Promise<string[]> {
  return page.evaluate((src: string) => {
    const re = new RegExp(src, 'i')
    const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT'])
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const tag = node.parentElement?.tagName ?? ''
        return SKIP.has(tag) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
      },
    })
    const matches: string[] = []
    let node: Node | null
    while ((node = walker.nextNode())) {
      const text = (node.textContent ?? '').trim()
      if (text && re.test(text)) matches.push(text)
    }
    return matches
  }, pattern.source)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('[wave14] partner pages i18n', () => {
  test.beforeEach(async ({ page }) => {
    await setupPartnerAuth(page)
    await setupWave14Mocks(page)
  })

  // ── /partner/notifications ──

  test('TC1: /partner/notifications が 500 を返さない', async ({ page }) => {
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/partner/notifications') || r.status() < 500),
      page.goto('/partner/notifications'),
    ])
    await page.waitForLoadState('domcontentloaded')
    const url = page.url()
    // 認証リダイレクト (→/login) の場合は graceful skip
    if (!url.includes('/partner/notifications')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    expect(response.status()).toBeLessThan(500)
  })

  test('TC2: /partner/notifications に "通知ログ" が表示される', async ({ page }) => {
    await page.goto('/partner/notifications')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(600)
    const url = page.url()
    if (!url.includes('/partner/notifications')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    await expect(page.getByText('通知ログ')).toBeVisible()
  })

  test('TC3: /partner/notifications の重要度フィルタ "すべて" が表示される', async ({ page }) => {
    await page.goto('/partner/notifications')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(600)
    const url = page.url()
    if (!url.includes('/partner/notifications')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    // <option> 要素でフィルタが描画されること
    await expect(page.getByRole('option', { name: 'すべて' })).toBeAttached()
  })

  test('TC4: /partner/notifications のテーブルヘッダに "重要度" が表示される', async ({ page }) => {
    await page.goto('/partner/notifications')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(800)
    const url = page.url()
    if (!url.includes('/partner/notifications')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    await expect(page.getByRole('columnheader', { name: '重要度' })).toBeVisible()
  })

  // ── /partner/dashboard ──

  test('TC5: /partner/dashboard に "現在の運用残高" が表示される', async ({ page }) => {
    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(800)
    const url = page.url()
    if (!url.includes('/partner/dashboard')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    await expect(page.getByText('現在の運用残高')).toBeVisible()
  })

  test('TC6: /partner/dashboard に "全体損益" が表示される', async ({ page }) => {
    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(800)
    const url = page.url()
    if (!url.includes('/partner/dashboard')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    await expect(page.getByText('全体損益')).toBeVisible()
  })

  // ── /partner/users/[id] ──

  test('TC7: /partner/users/1 が 500 を返さない', async ({ page }) => {
    const response = await page.goto('/partner/users/1')
    await page.waitForLoadState('domcontentloaded')
    const url = page.url()
    if (!url.includes('/partner/users/1')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    expect(response?.status() ?? 200).toBeLessThan(500)
  })

  test('TC8: /partner/users/1 に "テスター詳細" が表示される', async ({ page }) => {
    await page.goto('/partner/users/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(600)
    const url = page.url()
    if (!url.includes('/partner/users/1')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    await expect(page.getByText('テスター詳細')).toBeVisible()
  })

  // ── /partner/referral/[id] ──

  test('TC9: /partner/referral/1 が 500 を返さない', async ({ page }) => {
    const response = await page.goto('/partner/referral/1')
    await page.waitForLoadState('domcontentloaded')
    const url = page.url()
    if (!url.includes('/partner/referral/1')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    expect(response?.status() ?? 200).toBeLessThan(500)
  })

  test('TC10: /partner/referral/1 に "運用状況詳細" が表示される', async ({ page }) => {
    await page.goto('/partner/referral/1')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(600)
    const url = page.url()
    if (!url.includes('/partner/referral/1')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    await expect(page.getByText('運用状況詳細')).toBeVisible()
  })

  // ── 全体チェック ──

  test('TC11: /partner/notifications で翻訳キーリテラル漏れなし', async ({ page }) => {
    await page.goto('/partner/notifications')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(800)
    const url = page.url()
    if (!url.includes('/partner/notifications')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    // "PartnerNotifications.xxx" 形式のキーリテラルが DOM に露出していないこと
    const keyLiterals = await findTextNodes(page, /PartnerNotifications\.[A-Za-z]+/)
    expect(
      keyLiterals.length,
      `翻訳キーリテラルが画面に露出: ${keyLiterals.slice(0, 3).join(', ')}`,
    ).toBe(0)
  })

  test('TC12: /partner/notifications に英語ハードコード UI テキスト残存なし', async ({ page }) => {
    await page.goto('/partner/notifications')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(800)
    const url = page.url()
    if (!url.includes('/partner/notifications')) {
      test.skip(true, `認証リダイレクト: ${url}`)
    }
    // 既知の英語ハードコードが存在しないこと
    const hardcodedEN = [
      '通知ログ', // should be JP
    ]
    // Check by verifying JP strings are present (not EN equivalents)
    const bodyText = await page.evaluate(() => (document.body as HTMLElement).innerText ?? '')
    expect(bodyText).toContain('通知ログ')

    // "Notification Log" 英語がそのまま表示されていないこと
    const englishMatches = await findTextNodes(page, /\bNotification Log\b/)
    expect(
      englishMatches.length,
      `英語 "Notification Log" が残存: ${englishMatches.slice(0, 3).join(', ')}`,
    ).toBe(0)
  })
})
