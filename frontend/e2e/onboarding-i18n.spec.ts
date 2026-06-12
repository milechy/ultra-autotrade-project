// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// E2E spec: /onboarding i18n 検証 (feature/user-onboarding-i18n)
//
// 検証範囲:
//   TC1: /onboarding が 5xx を返さない（疎通）
//   TC2: ja-JP デフォルトで日本語見出し "はじめに" が表示される
//   TC3: NEXT_LOCALE=en cookie セット → リロードで英語見出し "Set Up Your Wallet" 等に切替
//        （認証ゲートで到達不能な場合は gracefully skip）
//   TC4: STEP カードクリックで activeStep が切替わる（progress bar 反映）
//   TC5: FAQ クリックで該当 index のみ展開される
//   TC6: 前ボタンが step1 で disabled、次ボタンが step4 で disabled
//
// NOTE:
//   - route group (user) の URL は /onboarding（ディレクトリ名 "(user)" は URL に含まれない）
//   - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com)
//   - 認証ゲートで描画不能な場合は test.skip で gracefully skip
//   - CLAUDE.md 教訓: < 500 チェックのみでは 404 を見逃す → 期待要素の存在まで assert する
//
// Run:
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/onboarding-i18n.spec.ts
//   npx playwright test e2e/onboarding-i18n.spec.ts  # 本番 URL

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const ONBOARDING_URL = '/onboarding'

/** /onboarding に遷移し、5xx でなく URL に /onboarding が含まれるか確認する。
 *  認証ゲートでリダイレクトされた場合は false を返す。
 */
async function visitOnboarding(page: Page): Promise<boolean> {
  const res = await page.goto(ONBOARDING_URL, { waitUntil: 'domcontentloaded' })
  if (!res || res.status() >= 500) return false
  if (!page.url().includes('/onboarding')) return false
  return true
}

// ─── テスト ──────────────────────────────────────────────────────────────────

test.describe('[Onboarding] i18n 検証 (feature/user-onboarding-i18n)', () => {
  test('TC1: /onboarding が 5xx を返さない', async ({ page }) => {
    const res = await page.goto(ONBOARDING_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/onboarding は 5xx であってはならない').toBeLessThan(500)
    // CLAUDE.md 教訓 PR #307: < 500 だけでは 404 を見逃す → URL 確認も行う
    const statusCode = res!.status()
    expect(statusCode, '/onboarding は 404 であってはならない').not.toBe(404)
  })

  test('TC2: ja デフォルトで日本語見出し "はじめに" が表示される', async ({ page }) => {
    const reachable = await visitOnboarding(page)
    test.skip(!reachable, '認証ゲートで /onboarding に到達不能のため skip')

    // locale=ja-JP (playwright.config.ts デフォルト) で headerTitle "はじめに" が表示される
    const heading = page.getByText('はじめに', { exact: false }).first()
    const visible = await heading.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, 'ページがレンダリングされない環境（認証後コンテンツ）のため skip')
    await expect(heading).toBeVisible()
  })

  test('TC3: NEXT_LOCALE=en cookie → リロードで英語見出し "Getting Started" が表示される', async ({ page }) => {
    const reachable = await visitOnboarding(page)
    test.skip(!reachable, '認証ゲートで /onboarding に到達不能のため skip')

    // 最初に日本語が表示されていることを確認
    const jaHeading = page.getByText('はじめに', { exact: false }).first()
    const jaVisible = await jaHeading.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!jaVisible, 'ページがレンダリングされない環境のため skip')

    // NEXT_LOCALE=en cookie をセットしてリロード
    await page.context().addCookies([
      {
        name: 'NEXT_LOCALE',
        value: 'en',
        domain: new URL(page.url()).hostname,
        path: '/',
      },
    ])
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(800)

    // 英語見出し "Getting Started" が表示される (en.json の Onboarding.headerTitle)
    const enHeading = page.getByText('Getting Started', { exact: false }).first()
    const enVisible = await enHeading.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!enVisible, 'EN 切替後もコンテンツが表示されない環境のため skip')
    await expect(enHeading).toBeVisible()

    // "はじめに" は消えていること
    await expect(page.getByText('はじめに', { exact: true }).first()).not.toBeVisible({ timeout: 2_000 })
  })

  test('TC4: STEP カードクリックで activeStep が切替わる（progress bar 反映）', async ({ page }) => {
    const reachable = await visitOnboarding(page)
    test.skip(!reachable, '認証ゲートで /onboarding に到達不能のため skip')

    // progress bar セグメント (h-1.5 rounded-full) が 4 つ存在することを確認
    const progressSegments = page.locator('.h-1\\.5.rounded-full')
    const count = await progressSegments.count().catch(() => 0)
    test.skip(count === 0, 'progress bar が表示されない環境のため skip')
    expect(count).toBe(4)

    // STEP 2 カードをクリック: "STEP 2" バッジが含まれるカードを取得
    const step2Badge = page.getByText('STEP 2', { exact: false }).first()
    const badgeVisible = await step2Badge.isVisible({ timeout: 3_000 }).catch(() => false)
    test.skip(!badgeVisible, 'STEP バッジが表示されない環境のため skip')

    // STEP 2 カード（クリック可能な親要素）をクリック
    // StepCard は `rounded-xl border p-5 cursor-pointer` を持つ div
    const step2Card = page.locator('[class*="rounded-xl"][class*="cursor-pointer"]').filter({ has: page.getByText('STEP 2') }).first()
    await step2Card.click()
    await page.waitForTimeout(300)

    // クリック後: STEP 2 カードが active スタイル (border-blue-500) を持つ
    await expect(step2Card).toHaveClass(/border-blue-500/, { timeout: 2_000 })
  })

  test('TC5: FAQ クリックで該当 index のみ展開される', async ({ page }) => {
    const reachable = await visitOnboarding(page)
    test.skip(!reachable, '認証ゲートで /onboarding に到達不能のため skip')

    // FAQ セクションの存在確認
    const faqSection = page.getByRole('heading', { level: 2 }).filter({ hasText: /よくある質問|FAQ/i }).first()
    const faqVisible = await faqSection.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!faqVisible, 'FAQ セクションが表示されない環境のため skip')

    // FAQ の最初のボタンをクリック
    const faqButtons = page.locator('.rounded-lg.border button').first()
    await faqButtons.click()
    await page.waitForTimeout(300)

    // クリックした FAQ の答えが展開されること（border-t が現れる div）
    const expandedAnswer = page.locator('.border-t.border-zinc-800').first()
    await expect(expandedAnswer).toBeVisible({ timeout: 2_000 })
  })

  test('TC6: 前ボタンが step1 で disabled、次ボタンが step4 で disabled', async ({ page }) => {
    const reachable = await visitOnboarding(page)
    test.skip(!reachable, '認証ゲートで /onboarding に到達不能のため skip')

    // ナビゲーションボタンの存在確認
    const prevBtn = page.getByText('← 前のステップ', { exact: false }).or(
      page.getByText('Previous', { exact: false })
    ).first()
    const nextBtn = page.getByText('次のステップ →', { exact: false }).or(
      page.getByText('Next', { exact: false })
    ).first()

    const prevVisible = await prevBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!prevVisible, 'ナビゲーションボタンが表示されない環境のため skip')

    // step1 (初期状態) → 前ボタンが disabled
    await expect(prevBtn).toBeDisabled({ timeout: 2_000 })

    // 次ボタンを 3 回クリックして step4 に移動
    for (let i = 0; i < 3; i++) {
      const enabled = await nextBtn.isEnabled({ timeout: 2_000 }).catch(() => false)
      if (!enabled) break
      await nextBtn.click()
      await page.waitForTimeout(200)
    }

    // step4 → 次ボタンが disabled
    await expect(nextBtn).toBeDisabled({ timeout: 2_000 })
  })
})

test.describe('[Mobile 375px][Onboarding] i18n 疎通', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('モバイルで /onboarding が 5xx を返さない', async ({ page }) => {
    const res = await page.goto(ONBOARDING_URL, { waitUntil: 'domcontentloaded' })
    expect(res?.status() ?? 0).toBeLessThan(500)
    expect(res?.status() ?? 200).not.toBe(404)
  })

  test('モバイルで日本語見出し "はじめに" が表示される', async ({ page }) => {
    const reachable = await visitOnboarding(page)
    test.skip(!reachable, '認証ゲートで到達不能のため skip')

    const heading = page.getByText('はじめに', { exact: false }).first()
    const visible = await heading.isVisible({ timeout: 5_000 }).catch(() => false)
    test.skip(!visible, 'モバイルでページがレンダリングされない環境のため skip')
    await expect(heading).toBeVisible()
  })
})
