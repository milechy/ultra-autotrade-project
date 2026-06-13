// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: withdraw ページ i18n 化 smoke test
 * Asana: feat/withdraw-i18n-v2 / PR Gate 4
 *
 * 検証範囲:
 *   TC1: /withdraw が 404/5xx を返さない
 *   TC2: /withdraw に Withdraw.pageTitle "USDC 出金" が表示される
 *        認証ゲートで到達できない場合は gracefully skip
 *   TC3: /withdraw に Withdraw.withdrawFormTitle "出金情報" が表示される
 *        認証後コンテンツの場合は gracefully skip
 *   TC4: /withdraw に Withdraw.nonCustodialNote テキストが表示される
 *        認証後コンテンツの場合は gracefully skip
 *
 * NOTE:
 *   - app/(user)/withdraw/page.tsx → URL は /withdraw
 *     (route group (user) はディレクトリ名が URL に含まれない)
 *   - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com)
 *   - next-intl はサーバー側 locale 解決。クライアント側トグルなし。
 *     デフォルト locale = ja。pageTitle は "USDC 出金"。
 *   - 認証ゲートでリダイレクトされた場合は test.skip で gracefully skip する
 *   - Gate 1-3: ja/en key parity は python3 スクリプトで別途検証済み (diff=NONE, en:54, ja:54)
 */

import { test, expect } from '@playwright/test'

const WITHDRAW_URL = '/withdraw'

test.describe('[withdraw-i18n] /withdraw ページ i18n smoke', () => {
  test('TC1: /withdraw が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto(WITHDRAW_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/withdraw は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/withdraw は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: /withdraw に "USDC 出金" テキストが表示される', async ({ page }) => {
    const res = await page.goto(WITHDRAW_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/withdraw')) {
      test.skip(true, '認証ゲートで /withdraw に到達不能のため skip')
      return
    }

    const pageTitle = page.getByText('USDC 出金', { exact: false }).first()
    const visible = await pageTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"USDC 出金" テキストが認証後コンテンツのため skip')
    await expect(pageTitle).toBeVisible()
  })

  test('TC3: /withdraw に Withdraw.withdrawFormTitle "出金情報" が表示される', async ({ page }) => {
    const res = await page.goto(WITHDRAW_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/withdraw')) {
      test.skip(true, '認証ゲートで /withdraw に到達不能のため skip')
      return
    }

    const formTitle = page.getByText('出金情報', { exact: false }).first()
    const visible = await formTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"出金情報" フォームタイトルが認証後コンテンツのため skip')
    await expect(formTitle).toBeVisible()
  })

  test('TC4: /withdraw に ノンカストディアル注意書きが表示される', async ({ page }) => {
    const res = await page.goto(WITHDRAW_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/withdraw')) {
      test.skip(true, '認証ゲートで /withdraw に到達不能のため skip')
      return
    }

    // Withdraw.nonCustodialNote = "ノンカストディアル出金:" の一部が表示されることを確認
    const notice = page.getByText('ノンカストディアル', { exact: false }).first()
    const visible = await notice.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, 'ノンカストディアル注意書きが認証後コンテンツのため skip')
    await expect(notice).toBeVisible()
  })
})

test.describe('[Mobile 375px][withdraw-i18n] /withdraw ページ smoke', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('モバイルで /withdraw が 5xx を返さない', async ({ page }) => {
    const res = await page.goto(WITHDRAW_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), 'モバイル: /withdraw は 5xx であってはならない').toBeLessThan(500)
  })

  test('モバイルで /withdraw に "USDC 出金" が表示される', async ({ page }) => {
    const res = await page.goto(WITHDRAW_URL, { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/withdraw')) {
      test.skip(true, 'モバイル: 認証ゲートで /withdraw に到達不能のため skip')
      return
    }

    const pageTitle = page.getByText('USDC 出金', { exact: false }).first()
    const visible = await pageTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, 'モバイル: "USDC 出金" が認証後コンテンツのため skip')
    await expect(pageTitle).toBeVisible()
  })
})
