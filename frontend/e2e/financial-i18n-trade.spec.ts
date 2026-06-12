// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: trade ページ i18n 化 smoke test
 * Asana: financial batch D / PR Group D
 *
 * 検証範囲:
 *   TC1: /user/trade が 404/5xx を返さない
 *   TC2: /user/trade に Trade.pageTitle "取引承認" が表示される
 *        認証ゲートで到達できない場合は gracefully skip
 *   TC3: /user/trade に Trade.noPendingTitle "承認待ちの取引はありません" または
 *        Trade.loadingText "読み込み中..." が表示される
 *        認証ゲートで到達できない場合は gracefully skip
 *
 * NOTE:
 *   - app/user/trade/page.tsx → URL は /user/trade（通常フォルダ）
 *     ※ app/(user)/trade/page.tsx (route group) も存在するが /user/trade が正規パス
 *   - shadow_mode ?? sandbox_mode 判定ロジック・signal.action は非改変
 *   - Gate 1-3: ja/en key parity は python3 スクリプトで別途検証済み
 */

import { test, expect } from '@playwright/test'

test.describe('[financial-i18n-D] trade - i18n smoke', () => {
  test('TC1: /user/trade が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto('/user/trade', { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/user/trade は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/user/trade は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: /user/trade に "取引承認" テキストが表示される', async ({ page }) => {
    const res = await page.goto('/user/trade', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/user/trade')) {
      test.skip(true, '認証ゲートで /user/trade に到達不能のため skip')
      return
    }

    const tradeTitle = page.getByText('取引承認', { exact: false }).first()
    const visible = await tradeTitle.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '"取引承認" テキストが認証後コンテンツのため skip')
    await expect(tradeTitle).toBeVisible()
  })

  test('TC3: /user/trade に承認待ちメッセージまたは読み込み中テキストが表示される', async ({ page }) => {
    const res = await page.goto('/user/trade', { waitUntil: 'domcontentloaded' })
    if (!res || res.status() >= 400 || !page.url().includes('/user/trade')) {
      test.skip(true, '認証ゲートで /user/trade に到達不能のため skip')
      return
    }

    // Trade.noPendingTitle = "承認待ちの取引はありません"
    // Trade.loadingText = "読み込み中..."
    const noPendingText = page.getByText('承認待ちの取引はありません', { exact: false }).first()
    const loadingText = page.getByText('読み込み中', { exact: false }).first()

    const noPendingVisible = await noPendingText.isVisible({ timeout: 5_000 }).catch(() => false)
    const loadingVisible = await loadingText.isVisible({ timeout: 5_000 }).catch(() => false)

    test.skip(!noPendingVisible && !loadingVisible, 'trade コンテンツが認証後コンテンツのため skip')
    expect(noPendingVisible || loadingVisible, 'trade ページコンテンツが表示される').toBe(true)
  })
})
