// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// LIFF チャット 紹介キャンペーンパネル (ReferralPanel) の最小 E2E。
//
// 検証範囲:
//   TC1: ハンバーガーメニュー → 「紹介キャンペーン」パネルを開ける
//   TC2: /api/referral/earnings をモックし、合計報酬・紹介人数が描画される
//   TC3: 紹介コードのコピーボタンが存在し、トーストが出る
//   TC4: シェア導線 (LINE / メール / リンクコピー) が描画される
//   TC5: 報酬の仕組み 3 ステップが描画される
//
// 方式: page.route で /api/referral/earnings を傍受 (バックエンド不要)。
//   ReferralPanel はハンバーガーメニュー (client state) から開くため、
//   URL param ではなくメニュー操作で到達する。
//
// baseURL は playwright.config.ts の use.baseURL (STAGING_URL ||
//   https://app.ultra-auto-trade.com) を継承する。
//
// 注意: 本 spec は実行しない (Lane 規約)。配線/要素存在の最小カバレッジのみ。

import { test, expect, type Page } from '@playwright/test'

// ─── モックデータ ─────────────────────────────────────────────────────────────

const MOCK_EARNINGS = {
  referral_count: 2,
  current_month_reward_jpy: '1500',
  total_payout_jpy: '4500',
  campaign_rate: '30',
  referral_code: 'AB12CD34',
  referred_users: [
    {
      name: '山田太郎',
      joined_at: '2026-05-01T00:00:00+00:00',
      status: '運用中',
      reward_jpy: '3000',
    },
    {
      name: '佐藤花子',
      joined_at: '2026-05-20T00:00:00+00:00',
      status: '登録済み',
      reward_jpy: '1500',
    },
  ],
}

// ─── ヘルパー ─────────────────────────────────────────────────────────────────

/** /api/referral/earnings を傍受してモックを返す。 */
async function mockReferralApi(page: Page): Promise<void> {
  await page.route('**/api/referral/earnings', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_EARNINGS),
    })
  })
}

/** liff-chat を開き、ハンバーガー → 紹介キャンペーンパネルを開く。 */
async function openReferralPanel(page: Page): Promise<void> {
  await page.goto('/liff-chat')
  // ハンバーガートグル (aria-label="メニューを開く")
  await page.getByRole('button', { name: 'メニューを開く' }).click()
  // メニュー項目「紹介キャンペーン」
  await page.getByRole('button', { name: /紹介キャンペーン/ }).click()
}

// ─── テスト ───────────────────────────────────────────────────────────────────

test.describe('LIFF チャット 紹介キャンペーンパネル', () => {
  test.beforeEach(async ({ page }) => {
    await mockReferralApi(page)
  })

  test('TC1+TC2: パネルを開くと合計報酬・紹介人数が描画される', async ({ page }) => {
    await openReferralPanel(page)

    // 合計報酬 (¥4,500 = total_payout_jpy)
    await expect(page.getByText('¥4,500')).toBeVisible()
    // 紹介人数のサマリー文言
    await expect(page.getByText(/2名の紹介から獲得/)).toBeVisible()
  })

  test('TC3: 紹介コードとコピーボタンが描画される', async ({ page }) => {
    await openReferralPanel(page)

    await expect(page.getByText('AB12CD34')).toBeVisible()

    const copyBtn = page.getByRole('button', { name: 'コピー' })
    await expect(copyBtn).toBeVisible()
  })

  test('TC4: シェア導線 (LINE / メール / リンクコピー) が描画される', async ({ page }) => {
    await openReferralPanel(page)

    await expect(page.getByRole('button', { name: /LINEで送る/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /メールで送る/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /リンクをコピー/ })).toBeVisible()
  })

  test('TC5: 報酬の仕組み 3 ステップが描画される', async ({ page }) => {
    await openReferralPanel(page)

    await expect(page.getByText('報酬の仕組み')).toBeVisible()
    await expect(page.getByText('友達に紹介コードを送る')).toBeVisible()
    await expect(page.getByText('友達が登録・運用開始')).toBeVisible()
  })

  test('TC6: 紹介した友達リストがステータス付きで描画される', async ({ page }) => {
    await openReferralPanel(page)

    await expect(page.getByText('山田太郎')).toBeVisible()
    await expect(page.getByText('佐藤花子')).toBeVisible()
    await expect(page.getByText('運用中')).toBeVisible()
  })
})
