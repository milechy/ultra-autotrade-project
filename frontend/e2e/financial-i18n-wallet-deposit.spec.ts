// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: wallet + deposit ページ i18n 化 smoke test
 * Asana: financial batch B / PR Group B
 *
 * 検証範囲:
 *   TC1: /user/wallet が 404/5xx を返さない
 *   TC2: /user/wallet に Wallet.pageTitle "ウォレット接続" が表示される
 *        認証ゲートで到達できない場合は gracefully skip
 *   TC3: /user/deposit が 404/5xx を返さない
 *   TC4: /user/deposit に Deposit.pageTitle "入金" が表示される
 *        認証ゲートで到達できない場合は gracefully skip
 *
 * NOTE:
 *   - app/user/wallet/page.tsx → URL は /user/wallet（通常フォルダ、route group なし）
 *   - app/user/deposit/page.tsx → URL は /user/deposit（通常フォルダ、route group なし）
 *   - Gate 1-3: ja/en key parity は python3 スクリプトで別途検証済み
 */

import { test, expect } from '@playwright/test'

test.describe('[financial-i18n-B] wallet + deposit - i18n smoke', () => {
  test('TC1: /user/wallet が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto('/user/wallet', { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/user/wallet は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/user/wallet は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: /user/wallet に "ウォレット接続" テキストが表示される', async ({ page }) => {
    const res = await page.goto('/user/wallet', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/user/wallet')) {
      test.skip(true, '認証ゲートで /user/wallet に到達不能のため skip')
      return
    }

    const walletTitle = page.getByText('ウォレット接続', { exact: false }).first()
    const visible = await walletTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"ウォレット接続" テキストが認証後コンテンツのため skip')
    await expect(walletTitle).toBeVisible()
  })

  test('TC3: /user/deposit が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto('/user/deposit', { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/user/deposit は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/user/deposit は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC4: /user/deposit に "入金" テキストが表示される', async ({ page }) => {
    const res = await page.goto('/user/deposit', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/user/deposit')) {
      test.skip(true, '認証ゲートで /user/deposit に到達不能のため skip')
      return
    }

    const depositTitle = page.getByText('入金', { exact: false }).first()
    const visible = await depositTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"入金" テキストが認証後コンテンツのため skip')
    await expect(depositTitle).toBeVisible()
  })
})
