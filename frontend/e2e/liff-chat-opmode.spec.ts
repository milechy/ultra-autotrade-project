// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Lane opmode — LIFF chat 運用モード切替 (Tier B) (Asana 1215359346113656)
//
// 対象: frontend/app/(liff)/liff-chat/_components/panels/OpModePanel.tsx
//
// 検証内容:
//   1. 運用モードパネルを開き、API の現在モード (user_mode) が表示カードに反映される。
//   2. モード選択カード (完全おまかせ managed / アクティブ active) が 2 枚表示される。
//      Pro モードは非表示であること。
//   3. カードをタップすると確認ステップ無しで即 PUT /api/user/settings が
//      { user_mode } 形で呼ばれ、トースト「『モード名』に切り替えました」が出る。
//   4. NEXT_PUBLIC_DELEGATION_CONSENT_ENABLED が off (既定) のとき、「完全おまかせ」
//      カードは表示されるが選択不可 (disabled) であり、タップしても PUT されない
//      (2026-08-04 PR2: 縮退修正 — フラグ off で同意フローをスキップして状態表示
//      だけ変更していた不具合の再発防止)。
//
// 前提: NEXT_PUBLIC_AGGRESSIVE_TIER_ENABLED / NEXT_PUBLIC_DELEGATION_CONSENT_ENABLED は
// 未設定（既定 off）。両方 on の環境では「おまかせ」タップで運用方針シート
// (managed-scope-sheet) が挟まるため、3. の即時 PUT は成立しない。


//
// テスト戦略:
//   - /api/user/settings の GET/PUT を page.route で mock し、バックエンド非依存にする。
//   - getAuthToken() は localStorage の 'auth_token' を読むため addInitScript で事前注入。
//   - LIFF home → ハンバーガー → 「運用モード切替」でパネルへ遷移する。
//
// 実行方法 (このレーンでは実行しない):
//   npx playwright test e2e/liff-chat-opmode.spec.ts
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/liff-chat-opmode.spec.ts

import { test, expect, type Page } from '@playwright/test'

// PUT で受け取った user_mode を記録するための共有状態。
let lastPutMode: string | null = null

// auth token を事前注入し、/api/user/settings を mock する共通セットアップ。
async function setupOpModePage(page: Page, initialMode: 'managed' | 'active') {
  lastPutMode = null

  // getAuthToken() が読む正準キー 'auth_token' に token を入れておく。
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem('auth_token', 'e2e-test-token')
    } catch {
      /* ignore (private mode) */
    }
  })

  // user/settings GET / PUT を mock。
  await page.route('**/api/user/settings', async (route) => {
    const req = route.request()
    if (req.method() === 'PUT') {
      const body = req.postDataJSON() as { user_mode?: string }
      lastPutMode = body?.user_mode ?? null
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user_mode: lastPutMode }),
      })
      return
    }
    // GET (初回ロード)。terms_version は useLiffTermsGate (Asana 1215360586206558) が
    // 参照する重要事項同意ゲート判定用。未設定だと /liff-confirm へリダイレクトされる。
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ user_mode: initialMode, terms_version: 'liff-v4' }),
    })
  })
}

// LIFF home からハンバーガー経由で運用モードパネルを開く。
async function openOpModePanel(page: Page) {
  await page.goto('/liff-chat')
  // ハンバーガー (メニュー) を開く。
  await page.getByRole('button', { name: 'メニューを開く' }).click().catch(async () => {
    // aria-label が異なる場合のフォールバック。
    await page.getByText('運用モード切替').first().click()
  })
  // メニュー項目「運用モード切替」を押す。
  const menuItem = page.getByText('運用モード切替').first()
  if (await menuItem.isVisible().catch(() => false)) {
    await menuItem.click()
  }
  await expect(page.getByTestId('opmode-panel')).toBeVisible()
}

test.describe('LIFF 運用モード切替 (opmode)', () => {
  test('現在モードが表示カードに反映される', async ({ page }) => {
    await setupOpModePage(page, 'managed')
    await openOpModePanel(page)

    // 現在モードカードに「おまかせ」が反映される (ja.json Liff.panels.opMode.managedLabel)。
    await expect(page.getByTestId('opmode-current')).toHaveText('おまかせ')
  })

  test('モード選択カードが 2 枚表示され Pro は非表示', async ({ page }) => {
    await setupOpModePage(page, 'managed')
    await openOpModePanel(page)

    await expect(page.getByTestId('opmode-option-managed')).toBeVisible()
    await expect(page.getByTestId('opmode-option-active')).toBeVisible()
    // Pro モードのカードは存在しないこと。
    await expect(page.getByTestId('opmode-option-pro')).toHaveCount(0)
    await expect(page.getByText('Pro', { exact: false })).toHaveCount(0)
  })

  test('カードタップで即 PUT され切替トーストが出る', async ({ page }) => {
    await setupOpModePage(page, 'managed')
    await openOpModePanel(page)

    // 「アクティブ」を選択 — 確認ステップ無しで即切替。
    await page.getByTestId('opmode-option-active').click()

    // トースト「『アクティブ』に切り替えました」を確認。
    const toast = page.getByTestId('opmode-toast')
    await expect(toast).toBeVisible()
    await expect(toast).toContainText('アクティブ')
    await expect(toast).toContainText('切り替えました')

    // PUT /api/user/settings が { user_mode: 'active' } で呼ばれたこと。
    expect(lastPutMode).toBe('active')

    // 表示カードも新モードに更新される。
    await expect(page.getByTestId('opmode-current')).toHaveText('アクティブ')
  })

  test('同一モードの再タップでは PUT しない', async ({ page }) => {
    // CONSENT_ENABLED off では managed カードが disabled になるため、
    // active モードでの再タップで同じ回帰意図 (同一モード再タップで PUT しない) を検証する。
    await setupOpModePage(page, 'active')
    await openOpModePanel(page)

    await page.getByTestId('opmode-option-active').click()
    // 既に active なので PUT は発火しない。
    expect(lastPutMode).toBeNull()
  })

  test('CONSENT_ENABLED off のとき「完全おまかせ」は選択不可', async ({ page }) => {
    await setupOpModePage(page, 'active')
    await openOpModePanel(page)

    // カードは表示されるが disabled (2026-08-04 PR2: 縮退修正)。
    await expect(page.getByTestId('opmode-option-managed')).toBeVisible()
    await expect(page.getByTestId('opmode-option-managed')).toBeDisabled()

    // クリックしても PUT が発火しない (disabled のため actionability check で弾かれる)。
    expect(lastPutMode).toBeNull()
  })
})
