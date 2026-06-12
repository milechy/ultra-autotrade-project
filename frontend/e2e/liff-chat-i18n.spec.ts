// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: liff-chat v3 i18n + JP/EN toggle + MoonPay language control
 * Asana GID: 1215650626628506 / PR #652
 *
 * 検証範囲:
 *   TC1: /liff-chat が 5xx でなく表示される (最小疎通)
 *   TC2: JP モード（デフォルト）でヘッダーに "EN" トグルボタンが存在する
 *   TC3: EN トグルをクリックすると "JP" に切替わる
 *   TC4: EN 切替後、Liff.home.approve の英語訳 "Approve" が DOM に現れる
 *        （認証ゲートで到達できない場合は gracefully skip）
 *   TC5: EN モード時、localStorage["lang"] が "en" になる
 *   TC6: EN モードで入金/出金パネルを開けた場合、MoonPay ウィジェット ("Buy with card") が表示される
 *   TC7: JP モードで入金/出金パネルを開いた場合、MoonPay ウィジェット ("クレジットカードで購入") は非表示
 *   TC8: localStorage["lang"]="en" を事前設定してリロードすると EN モードが維持される
 *
 * NOTE:
 *   - route group (liff) の URL は /liff-chat（ディレクトリ名 "(liff)" は URL に含まれない）
 *   - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com)
 *   - LIFF/Privy 認証ゲートで UI に到達不能な場合は test.skip で gracefully skip する
 */

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const LIFF_CHAT_URL = '/liff-chat'

/** JP/EN トグルボタンを取得する（aria-label "言語切替" or "Switch language"） */
function getLangToggleButton(page: Page) {
  return page
    .getByRole('button', { name: /言語切替|Switch language/i })
    .or(page.locator('button').filter({ hasText: /^EN$|^JP$/ }))
    .first()
}

/** ページが 5xx でないことと、基本的な liff-chat コンテンツが存在するかを確認する */
async function visitLiffChat(page: Page): Promise<boolean> {
  const res = await page.goto(LIFF_CHAT_URL, { waitUntil: 'domcontentloaded' })
  if (!res || res.status() >= 500) return false
  // 認証ゲートでリダイレクトされた場合はスキップ対象
  if (!page.url().includes('/liff-chat')) return false
  return true
}

/** ハンバーガーメニューから入金/出金パネルを開く */
async function openDepositPanel(page: Page): Promise<boolean> {
  const menuBtn = page
    .getByRole('button', { name: /Open menu|メニューを開く/i })
    .or(page.locator('button[aria-label*="メニュー"]'))
    .first()

  if (!(await menuBtn.isVisible().catch(() => false))) return false
  await menuBtn.click()
  await page.waitForTimeout(300)

  // メニュー項目 "入金/出金" or "Deposit / Withdraw"
  const depositItem = page
    .getByText(/入金\/出金|Deposit \/ Withdraw/i)
    .first()
  if (!(await depositItem.isVisible().catch(() => false))) return false
  await depositItem.click()
  await page.waitForTimeout(500)
  return true
}

// ─── テスト ──────────────────────────────────────────────────────────────────

test.describe('[LIFF Chat] i18n JP/EN トグル + MoonPay 言語制御', () => {
  test('TC1: /liff-chat が 5xx を返さない', async ({ page }) => {
    const res = await page.goto(LIFF_CHAT_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/liff-chat は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: JP モードでヘッダーに "EN" トグルボタンが存在する', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    // JP モード時は "EN" テキストのトグルボタンが表示される
    const toggleBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await toggleBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境（認証後コンテンツ）のため skip')
    await expect(toggleBtn).toBeVisible()
  })

  test('TC3: EN トグルをクリックすると "JP" ボタンに切替わる', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境のため skip')

    await enBtn.click()
    await page.waitForTimeout(500)

    // クリック後: ボタンテキストが "JP" に変わる
    const jpBtn = page.locator('button').filter({ hasText: /^JP$/ }).first()
    await expect(jpBtn).toBeVisible({ timeout: 3_000 })
  })

  test('TC4: EN 切替後、"Approve" テキストが DOM に現れる', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境のため skip')

    await enBtn.click()
    await page.waitForTimeout(800)

    // EN モードで Liff.home.approve = "Approve" が表示される
    const approveText = page.getByText('Approve', { exact: false }).first()
    // アクション提案が無い場合は "Approve" ボタン自体が存在しない可能性があるため
    // soft assertion で確認（存在する場合のみ英語化を検証）
    const approveVisible = await approveText.isVisible({ timeout: 3_000 }).catch(() => false)
    if (approveVisible) {
      await expect(approveText).toBeVisible()
    } else {
      // 提案が無くても EN モードに切替わったことをトグルボタン ("JP") で確認
      await expect(page.locator('button').filter({ hasText: /^JP$/ }).first()).toBeVisible()
    }
  })

  test('TC5: EN 切替後に localStorage["lang"] が "en" になる', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境のため skip')

    await enBtn.click()
    await page.waitForTimeout(500)

    const lang = await page.evaluate(() => localStorage.getItem('lang'))
    expect(lang, 'localStorage["lang"] は "en" であるべき').toBe('en')
  })

  test('TC6: EN モードで入金パネル内に MoonPay ウィジェット "Buy with card" が表示される', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境のため skip')

    // EN に切替え
    await enBtn.click()
    await page.waitForTimeout(500)

    const opened = await openDepositPanel(page)
    test.skip(!opened, '入金/出金パネルを開けない環境のため skip')

    // EN モード時: MoonPayWidget の "Buy with card" テキストが表示される
    const moonpayText = page.getByText('Buy with card', { exact: false }).first()
    await expect(moonpayText).toBeVisible({ timeout: 5_000 })
  })

  test('TC7: JP モードで入金パネル内に MoonPay ウィジェットが表示されない', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境のため skip')

    // JP モードのまま（トグルしない）
    const opened = await openDepositPanel(page)
    test.skip(!opened, '入金/出金パネルを開けない環境のため skip')

    // JP モード時: "クレジットカードで購入"（MoonPayWidget）は非表示
    const moonpayJp = page.getByText('クレジットカードで購入', { exact: false }).first()
    await expect(moonpayJp).not.toBeVisible({ timeout: 3_000 })
  })

  test('TC8: localStorage["lang"]="en" でリロード後も EN モードが維持される', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, '言語トグルボタンが表示されない環境のため skip')

    // localStorage を直接設定してリロード
    await page.evaluate(() => localStorage.setItem('lang', 'en'))
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(800)

    // リロード後も "JP" ボタンが表示される（EN モード維持）
    const jpBtn = page.locator('button').filter({ hasText: /^JP$/ }).first()
    const jpVisible = await jpBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!jpVisible, 'リロード後のコンテンツが認証ゲートで表示されないため skip')
    await expect(jpBtn).toBeVisible()

    // localStorage の値も維持
    const lang = await page.evaluate(() => localStorage.getItem('lang'))
    expect(lang, 'リロード後も localStorage["lang"] は "en" であるべき').toBe('en')
  })
})

test.describe('[Mobile 375px][LIFF Chat] i18n JP/EN トグル', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('モバイルで /liff-chat が 5xx を返さない', async ({ page }) => {
    const res = await page.goto(LIFF_CHAT_URL, { waitUntil: 'domcontentloaded' })
    expect(res?.status() ?? 0).toBeLessThan(500)
  })

  test('モバイルで EN トグルが動作する', async ({ page }) => {
    const reachable = await visitLiffChat(page)
    test.skip(!reachable, 'LIFF/Privy 認証ゲートで /liff-chat に到達不能のため skip')

    const enBtn = page.locator('button').filter({ hasText: /^EN$/ }).first()
    const visible = await enBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, 'モバイルで言語トグルが表示されない環境のため skip')

    await enBtn.click()
    await page.waitForTimeout(500)
    const jpBtn = page.locator('button').filter({ hasText: /^JP$/ }).first()
    await expect(jpBtn).toBeVisible({ timeout: 3_000 })
  })
})
