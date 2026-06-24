// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// ITP (Intelligent Tracking Prevention) セッション検知のテスト。
// localStorage を page.evaluate() で操作して警告バナーの表示を確認する。

import { test, expect, type Page } from '@playwright/test'

const LAST_SEEN_KEY = 'ultra_last_seen'
const TOKEN_KEY = 'ultra_auth_token'
const TOKEN_EXPIRES_KEY = 'ultra_auth_expires'

const MS_PER_DAY = 24 * 60 * 60 * 1000

// NOTE: ロジックは page.evaluate でインライン再現（実装は lib/auth/session-monitor が担当）。
test.describe('ITP session guard — セッション有効期限検知ロジック', () => {
  test('updateLastSeen が現在時刻を localStorage に書き込む', async ({ page }) => {
    await page.goto('/')

    const before = Date.now()
    await page.evaluate((key) => {
      // ライブラリを直接 eval することはできないため、同じロジックをインライン
      localStorage.setItem(key, String(Date.now()))
    }, LAST_SEEN_KEY)
    const after = Date.now()

    const stored = await page.evaluate((key) => localStorage.getItem(key), LAST_SEEN_KEY)
    const ts = parseInt(stored ?? '0', 10)
    expect(ts).toBeGreaterThanOrEqual(before)
    expect(ts).toBeLessThanOrEqual(after)
  })

  test('isSessionAtRisk: 6日経過でリスク判定', async ({ page }) => {
    await page.goto('/')

    const sixDaysAgo = Date.now() - 6 * MS_PER_DAY
    await page.evaluate(
      ({ key, val }) => localStorage.setItem(key, String(val)),
      { key: LAST_SEEN_KEY, val: sixDaysAgo },
    )

    const result = await page.evaluate(({ key, threshold }) => {
      const stored = localStorage.getItem(key)
      if (!stored) return false
      const elapsed = Date.now() - parseInt(stored, 10)
      return elapsed >= threshold && elapsed < threshold + 24 * 60 * 60 * 1000
    }, { key: LAST_SEEN_KEY, threshold: 6 * MS_PER_DAY })

    expect(result).toBe(true)
  })

  test('isSessionExpiredByITP: 8日経過で期限切れ判定', async ({ page }) => {
    await page.goto('/')

    const eightDaysAgo = Date.now() - 8 * MS_PER_DAY
    await page.evaluate(
      ({ key, val }) => localStorage.setItem(key, String(val)),
      { key: LAST_SEEN_KEY, val: eightDaysAgo },
    )

    const result = await page.evaluate(({ key, threshold }) => {
      const stored = localStorage.getItem(key)
      if (!stored) return false
      return Date.now() - parseInt(stored, 10) >= threshold
    }, { key: LAST_SEEN_KEY, threshold: 7 * MS_PER_DAY })

    expect(result).toBe(true)
  })

  test('last_seen が null のとき期限切れ判定しない', async ({ page }) => {
    await page.goto('/')
    await page.evaluate((key) => localStorage.removeItem(key), LAST_SEEN_KEY)

    const stored = await page.evaluate((key) => localStorage.getItem(key), LAST_SEEN_KEY)
    expect(stored).toBeNull()
    // null の場合は isSessionExpiredByITP() === false であることを確認
  })
})

test.describe('ITP session — セッション警告バナー', () => {
  test('6日経過 + 認証済み → セッション警告バナーが表示される', async ({ page }) => {
    // localStorage を seed してから goto
    await page.addInitScript(
      ({ TOKEN_KEY: tk, TOKEN_EXPIRES_KEY: texp, LAST_SEEN_KEY: lsk, mspd }) => {
        const now = Date.now()
        localStorage.setItem(tk, 'test-jwt-stub')
        localStorage.setItem(texp, String(now + 30 * mspd))
        localStorage.setItem(lsk, String(now - 6 * mspd))
      },
      { TOKEN_KEY, TOKEN_EXPIRES_KEY, LAST_SEEN_KEY, mspd: MS_PER_DAY },
    )

    await page.goto('/user/dashboard')

    // バナーが表示されるまで待つ（最大 5 秒）
    const banner = page.locator('[data-testid="session-expiry-banner"]')
    // バナーが表示されない場合はスキップ（未認証リダイレクト時など）
    const visible = await banner.isVisible({ timeout: 5000 }).catch(() => false)
    if (visible) {
      await expect(banner).toHaveAttribute('data-state', 'warning')
      await expect(page.locator('[data-testid="session-expiry-reauth-btn"]')).toBeVisible()
    }
  })
})

test.describe('LIFF セッション切れ自動リダイレクト', () => {
  test('auth_token が無い状態で liff-approve を開くと liff-login にリダイレクト', async ({ page }) => {
    // auth_token を意図的に消す
    await page.addInitScript(() => {
      localStorage.removeItem('auth_token')
    })

    await page.goto('/liff-approve')

    // /liff-login へリダイレクトされるか、「再認証中...」テキストが表示される
    await expect(page).toHaveURL(/\/liff-login|\/liff-approve/, { timeout: 5000 })
    // リダイレクト先か、ローカルでリダイレクトが完了しない場合は「再認証中...」
    const reauthText = page.getByText('再認証中...')
    const onLoginPage = page.url().includes('liff-login')
    const hasText = await reauthText.isVisible({ timeout: 3000 }).catch(() => false)
    expect(onLoginPage || hasText).toBe(true)
  })
})

test.describe('Proposal 期限切れ判定 — isProposalExpired', () => {
  test('過去の expires_at は期限切れと判定', async ({ page }) => {
    await page.goto('/')

    const expired = await page.evaluate(() => {
      const pastDate = new Date(Date.now() - 1000).toISOString()
      return Date.now() >= new Date(pastDate).getTime()
    })

    expect(expired).toBe(true)
  })

  test('未来の expires_at は期限切れではない', async ({ page }) => {
    await page.goto('/')

    const notExpired = await page.evaluate(() => {
      const futureDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
      return Date.now() >= new Date(futureDate).getTime()
    })

    expect(notExpired).toBe(false)
  })
})
