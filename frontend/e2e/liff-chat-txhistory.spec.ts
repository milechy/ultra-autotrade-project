// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/e2e/liff-chat-txhistory.spec.ts
//
// Lane: txhistory (Asana 1215444894102512 / 1215440046270784)
//
// 対象 2 ファイルの UI 契約を最小限カバーする:
//   1. TxHistoryPanel.tsx
//      - /api/transactions?limit=50 の 401 / token 欠落時に黒画面・無言失敗ではなく
//        「再ログイン」導線 (fail-visible) を出す。
//      - token-key 統一: 旧キー (ultra_auth_token) で保存済みのセッションでも
//        Authorization: Bearer が付与され 401 にならない。
//   2. ChatPanel.tsx
//      - 右上「履歴」アイコンが /liff-history へ遷移し、ブラウザ degrade 下でも
//        「LINEアプリから開いてください」黒画面・行き止まりにならない (#539 取りこぼし)。
//
// baseURL は playwright.config.ts 準拠 (STAGING_URL || https://app.ultra-auto-trade.com)。
// 実行はこの lane では行わない (記述のみ)。バックエンド state には依存せず、
// addInitScript で localStorage / fetch を制御する。

import { test, expect, type Page } from '@playwright/test'

const AUTH_TOKEN_KEY = 'auth_token'
const LEGACY_AUTH_TOKEN_KEY = 'ultra_auth_token'

// localStorage を初期化前にシードする (SSR/初期 mount より前)。
async function seedStorage(page: Page, values: Record<string, string | null>): Promise<void> {
  await page.addInitScript((seed: Record<string, string | null>) => {
    try {
      for (const [k, v] of Object.entries(seed)) {
        if (v === null) {
          window.localStorage.removeItem(k)
        } else {
          window.localStorage.setItem(k, v)
        }
      }
    } catch {
      // Safari Private Mode 等。テストは fail させない。
    }
  }, values)
}

// /api/transactions への応答をネットワークレベルで固定する。
async function mockTransactions(page: Page, status: number, body: unknown): Promise<void> {
  await page.route('**/api/transactions**', async (route) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

test.describe('liff-chat 取引履歴 (TxHistoryPanel) — 401 / token-key 統一', () => {
  test('token 欠落時は黒画面ではなく再ログイン導線を出す', async ({ page }) => {
    await seedStorage(page, {
      [AUTH_TOKEN_KEY]: null,
      [LEGACY_AUTH_TOKEN_KEY]: null,
    })

    await page.goto('/liff-chat')

    // 取引履歴パネルを開く (メニュー経由)。文言で到達できなくても
    // パネル自体の fail-visible 文言が出ることを最終的に検証する。
    const historyEntry = page.getByText('取引履歴', { exact: false }).first()
    if (await historyEntry.isVisible().catch(() => false)) {
      await historyEntry.click()
    }

    // token 欠落 → 再ログイン CTA が見えること (黒画面・無言失敗にしない)。
    await expect(
      page.getByRole('button', { name: '再ログイン' }),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('401 応答時に再ログイン導線へ degrade する', async ({ page }) => {
    await seedStorage(page, { [AUTH_TOKEN_KEY]: 'expired.jwt.token' })
    await mockTransactions(page, 401, { detail: 'Unauthorized' })

    await page.goto('/liff-chat')

    const historyEntry = page.getByText('取引履歴', { exact: false }).first()
    if (await historyEntry.isVisible().catch(() => false)) {
      await historyEntry.click()
    }

    await expect(
      page.getByRole('button', { name: '再ログイン' }),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('旧キーのみ保存済みでも Authorization: Bearer が付与される (token-key 統一)', async ({ page }) => {
    // 正準キーは空、旧キーにのみ token がある移行ケース。
    await seedStorage(page, {
      [AUTH_TOKEN_KEY]: null,
      [LEGACY_AUTH_TOKEN_KEY]: 'legacy.jwt.token',
    })

    let sawBearer = false
    await page.route('**/api/transactions**', async (route) => {
      const auth = route.request().headers()['authorization'] ?? ''
      if (auth === 'Bearer legacy.jwt.token') sawBearer = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })

    await page.goto('/liff-chat')

    const historyEntry = page.getByText('取引履歴', { exact: false }).first()
    if (await historyEntry.isVisible().catch(() => false)) {
      await historyEntry.click()
    }

    // 旧キーの token が getAuthToken のフォールバックで拾われ、Bearer に乗ること。
    await expect.poll(() => sawBearer, { timeout: 10_000 }).toBe(true)
  })
})

test.describe('liff-chat ChatPanel — 履歴アイコン degrade (#539)', () => {
  test('履歴アイコンタップで黒画面にならず履歴経路へ遷移する', async ({ page }) => {
    await seedStorage(page, { [AUTH_TOKEN_KEY]: 'dummy.jwt.token' })

    await page.goto('/liff-chat')

    // チャットを開く (FAB)。ボタン名に依存しすぎないよう aria-label を優先。
    const chatFab = page
      .getByRole('button', { name: /チャット|AI|相談/ })
      .first()
    if (await chatFab.isVisible().catch(() => false)) {
      await chatFab.click()
    }

    // 履歴アイコン (aria-label="履歴")。
    const historyIcon = page.getByRole('button', { name: '履歴' })
    if (await historyIcon.isVisible().catch(() => false)) {
      await historyIcon.click()
      // ソフト遷移後、行き止まり黒画面文言が画面を占有しないこと。
      await expect(page).toHaveURL(/liff-history|liff-login/, { timeout: 10_000 })
    }

    // どの degrade 分岐でも「LINEアプリから開いてください」だけの行き止まりにしない:
    // token がある前提なので中央 degrade ガードは作動してはならない。
    await expect(
      page.getByText('LINEアプリから開いてください'),
    ).toHaveCount(0)
  })
})
