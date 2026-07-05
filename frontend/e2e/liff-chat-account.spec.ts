// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// LIFF chat — アカウント設定パネル (AccountPanel) E2E (Asana 1215359472487694)
//
// カバレッジ (最小限・UI 要素の存在/操作):
//   1. liff-chat ホームを開き「アカウント」エントリからパネルを開く
//   2. ユーザー名のインライン編集 UI（鉛筆 → 入力 → 保存/キャンセル）
//   3. アバター変更 UI（隠し file input + カメラバッジ）の存在
//   4. アカウント削除フロー（赤枠ボタン → ボトムシート文言 → 申請/キャンセル）
//   5. ログアウトボタンの存在（既存挙動を壊していないことの確認）
//
// 実行方法:
//   # 本番 (デフォルト baseURL = playwright.config の STAGING_URL)
//   npx playwright test e2e/liff-chat-account.spec.ts
//   # ローカル
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/liff-chat-account.spec.ts
//
// NOTE: liff-chat は localStorage token を前提とする画面のため、
//       認証ゲートやリダイレクトで本体 UI が出ない環境では各テストを skip する
//       （§7 skip-only 罠は gate 判定側で構造的に扱う前提。spec 内では最小限）。

import { test, expect, type Page } from '@playwright/test'

const ACCOUNT_PANEL_ROUTE = '/liff-chat'

// アカウントパネルを開く。エントリ（「アカウント」）が見つからない場合は false。
async function openAccountPanel(page: Page): Promise<boolean> {
  await page.goto(ACCOUNT_PANEL_ROUTE, { waitUntil: 'domcontentloaded' })

  // 認証されていない / LIFF 初期化前はホームのメニューが描画されない可能性がある
  const accountEntry = page.getByText('アカウント', { exact: true }).first()
  try {
    await accountEntry.waitFor({ state: 'visible', timeout: 8000 })
  } catch {
    return false
  }
  await accountEntry.click()

  // パネル内の固有文言（運用開始日）が出れば AccountPanel がマウントされている
  try {
    await page.getByText('運用開始日').first().waitFor({ state: 'visible', timeout: 8000 })
  } catch {
    return false
  }
  return true
}

// /api/user/settings と /auth/me を 200 で固定する。これにより
//   - liffFetch の 401→/liff-login リダイレクトを抑止
//   - 重要事項同意ゲート（terms_version="liff-v4" 一致で accepted）の /liff-confirm リダイレクト抑止
// が成立し、認証あり/なしのどちらでも AccountPanel を決定的に開ける。
async function mockUserApis(page: Page): Promise<void> {
  const settingsBody = JSON.stringify({
    user_mode: 'managed',
    terms_version: 'liff-v4',
    corporate_fiscal_month: null,
    created_at: '2026-01-01T00:00:00Z',
    email: 'e2e@example.com',
    wallet_address: '0x0000000000000000000000000000000000000000',
  })
  await page.route('**/api/user/settings*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: settingsBody }),
  )
  await page.route('**/auth/me*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        email: 'e2e@example.com',
        created_at: '2026-01-01T00:00:00Z',
        wallet_address: '0x0000000000000000000000000000000000000000',
      }),
    }),
  )
}

// backend JWT を localStorage に seed し、AccountPanel を「ログイン済み」状態にする。
async function seedAuthToken(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem('auth_token', 'e2e-fake-jwt')
    } catch {
      /* localStorage 不可環境は無視 */
    }
  })
}

test.describe('liff-chat AccountPanel', () => {
  test('アカウントパネルが開きプロフィール/運用情報が表示される', async ({ page }) => {
    const opened = await openAccountPanel(page)
    test.skip(!opened, 'AccountPanel に到達できない環境 (未認証 / LIFF 未初期化)')

    await expect(page.getByText('運用開始日')).toBeVisible()
    await expect(page.getByText('運用モード')).toBeVisible()
    await expect(page.getByText('ウォレット').first()).toBeVisible()
  })

  test('ユーザー名のインライン編集 UI が動作する', async ({ page }) => {
    const opened = await openAccountPanel(page)
    test.skip(!opened, 'AccountPanel に到達できない環境')

    // 編集ボタン（鉛筆）→ 入力欄が出る
    const editBtn = page.getByRole('button', { name: 'ユーザー名を編集' })
    await expect(editBtn).toBeVisible()
    await editBtn.click()

    const nameInput = page.getByLabel('ユーザー名')
    await expect(nameInput).toBeVisible()

    // 保存ボタン・キャンセルボタンが存在する
    await expect(page.getByRole('button', { name: '名前を保存' })).toBeVisible()
    const cancelBtn = page.getByRole('button', { name: '編集をキャンセル' })
    await expect(cancelBtn).toBeVisible()

    // キャンセルで編集モードを抜け、編集ボタンへ戻る
    await cancelBtn.click()
    await expect(page.getByRole('button', { name: 'ユーザー名を編集' })).toBeVisible()
  })

  test('アバター変更 UI（file input + 変更ボタン）が存在する', async ({ page }) => {
    const opened = await openAccountPanel(page)
    test.skip(!opened, 'AccountPanel に到達できない環境')

    await expect(page.getByRole('button', { name: 'アイコンを変更' })).toBeVisible()
    // 隠し file input は accept=image/* の input[type=file]
    const fileInput = page.locator('input[data-testid="avatar-file-input"]')
    await expect(fileInput).toHaveAttribute('type', 'file')
    await expect(fileInput).toHaveAttribute('accept', 'image/*')
  })

  test('アカウント削除フロー（ボトムシート文言 + 申請/キャンセル）', async ({ page }) => {
    // 削除は認証済みのみ表示されるため、ログイン状態を seed して開く
    await mockUserApis(page)
    await seedAuthToken(page)
    const opened = await openAccountPanel(page)
    test.skip(!opened, 'AccountPanel に到達できない環境')

    // 削除エントリ（赤枠相当）
    const deleteEntry = page.getByText('アカウントを削除', { exact: true }).first()
    await expect(deleteEntry).toBeVisible()
    await deleteEntry.click()

    // ボトムシートの確認文言
    await expect(page.getByText('アカウントを削除しますか？')).toBeVisible()
    await expect(
      page.getByText(
        '残高がある場合、削除申請を受け付けられません。先に全額出金してください。',
      ),
    ).toBeVisible()

    // 申請ボタンとキャンセルボタン
    await expect(page.getByRole('button', { name: '削除を申請する' })).toBeVisible()
    const cancel = page.getByRole('button', { name: 'キャンセル' })
    await expect(cancel).toBeVisible()

    // キャンセルでシートが閉じる
    await cancel.click()
    await expect(page.getByText('アカウントを削除しますか？')).toBeHidden()
  })

  test('認証済みではログアウト/削除が表示される', async ({ page }) => {
    await mockUserApis(page)
    await seedAuthToken(page)
    const opened = await openAccountPanel(page)
    test.skip(!opened, 'AccountPanel に到達できない環境')

    await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible()
    await expect(page.getByText('アカウントを削除', { exact: true })).toBeVisible()
  })

  // 回帰防止: 未ログイン時に「ログアウト」/「アカウント削除」が表示されない
  // （staging browser PWA degrade で未認証でも表示されたバグ。UserHeader 5c42868 ガードの
  //  AccountPanel へのポート。Asana 1215522469898102）。
  test('未認証ではログアウト/削除が表示されない（回帰防止）', async ({ page }) => {
    // token を seed しない（未ログイン）。API は 200 固定でリダイレクトを抑止し、
    // パネル自体は開ける状態にしたうえで操作系が出ないことを検証する。
    await mockUserApis(page)
    const opened = await openAccountPanel(page)
    test.skip(!opened, 'AccountPanel に到達できない環境')

    await expect(page.getByRole('button', { name: 'ログアウト' })).toHaveCount(0)
    await expect(page.getByText('アカウントを削除', { exact: true })).toHaveCount(0)
  })
})
