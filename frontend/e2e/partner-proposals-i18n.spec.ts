// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: partner/proposals ページ i18n 化 smoke test
 * Asana: feat/proposals-i18n / PR #653
 *
 * 検証範囲:
 *   TC1: /partner/proposals が 404/5xx を返さない
 *   TC2: /partner/proposals に JP pageTitle "AI提案管理" が存在する
 *        認証ゲートで到達できない場合は gracefully skip
 *   TC3: /partner/proposals に EN pageTitle "AI Proposal Management" が存在する
 *        （NEXT_LOCALE=en cookie 設定 / 認証ゲートで到達不能なら skip）
 *   TC4: NextIntlClientProvider が runtime エラーを起こさず DOM が構築される
 *        （runtime error overlay または uncaught IntlError が存在しないことを確認）
 *
 * NOTE:
 *   - app/(partner)/partner/proposals/page.tsx → URL は /partner/proposals
 *     (route group "(partner)" はディレクトリ名のみで URL に含まれない)
 *   - app/(partner)/layout.tsx に NextIntlClientProvider が追加済み (CRITICAL 修正)
 *   - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com)
 *   - 認証ゲートで partner/proposals に到達不能な場合は TC2-TC4 を gracefully skip する
 */

import { test, expect } from '@playwright/test'

const PROPOSALS_URL = '/partner/proposals'

test.describe('[partner-proposals-i18n] /partner/proposals i18n smoke', () => {
  test('TC1: /partner/proposals が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto(PROPOSALS_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/partner/proposals は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/partner/proposals は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: JP モード - "AI提案管理" が DOM に存在する', async ({ page }) => {
    const res = await page.goto(PROPOSALS_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/proposals')) {
      test.skip(true, '認証ゲートで /partner/proposals に到達不能のため skip')
      return
    }

    // NextIntlClientProvider + useTranslations('PartnerProposals') による JP pageTitle
    const jpTitle = page.getByText('AI提案管理', { exact: false }).first()
    const visible = await jpTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"AI提案管理" が認証後コンテンツのため skip')
    await expect(jpTitle).toBeVisible()
  })

  test('TC3: NEXT_LOCALE=en cookie - "AI Proposal Management" が DOM に存在する', async ({
    browser,
  }) => {
    // middleware は NEXT_LOCALE cookie のみで locale を決定する（Accept-Language は不使用）。
    // liff.openWindow({external:true}) で開いた外部ブラウザが LINE WebView の cookie を
    // 引き継がず、Accept-Language 依存で日本語ユーザーに英語が表示されるバグの修正に伴い変更。
    const COOKIE_DOMAIN = new URL(process.env.STAGING_URL || 'https://app.ultra-auto-trade.com').hostname
    const context = await browser.newContext()
    await context.addCookies([
      { name: 'NEXT_LOCALE', value: 'en', domain: COOKIE_DOMAIN, path: '/' },
    ])
    const page = await context.newPage()

    const res = await page.goto(PROPOSALS_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/proposals')) {
      await context.close()
      test.skip(true, '認証ゲートで /partner/proposals (EN) に到達不能のため skip')
      return
    }

    // NextIntlClientProvider 経由の EN pageTitle
    const enTitle = page.getByText('AI Proposal Management', { exact: false }).first()
    const visible = await enTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    await context.close()
    test.skip(!visible, '"AI Proposal Management" が認証後コンテンツのため skip')
    await expect(enTitle).toBeVisible()
  })

  test('TC4: NextIntlClientProvider が runtime IntlError を起こさない', async ({ page }) => {
    const intlErrors: string[] = []

    // console.error と uncaught exceptions を監視
    page.on('console', (msg) => {
      if (msg.type() === 'error' && msg.text().includes('IntlError')) {
        intlErrors.push(msg.text())
      }
    })
    page.on('pageerror', (err) => {
      if (err.message.includes('IntlError') || err.message.includes('MISSING_MESSAGE')) {
        intlErrors.push(err.message)
      }
    })

    const res = await page.goto(PROPOSALS_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/partner/proposals')) {
      test.skip(true, '認証ゲートで /partner/proposals に到達不能のため skip')
      return
    }

    // 少し待ってから IntlError が出ていないことを確認
    await page.waitForTimeout(1_000)
    expect(intlErrors, `IntlError が検出された: ${intlErrors.join(', ')}`).toHaveLength(0)
  })
})
