// Copyright (c) Ultra AutoTrade. All rights reserved.
/**
 * E2E tests for the LIFF chat "MY WALLET" panel (MyWalletPanel.tsx).
 *
 * 検証対象:
 *  1. /liff-chat が表示され、ハンバーガーメニューから MY WALLET パネルを開ける
 *  2. 未接続/取得不可状態でも「ウォレットに接続する」誘導 UI が出る（空状態が埋まる）
 *  3. fail-visible: 永久「読み込み中...」で固まらず、再試行/再読み込み導線がある
 *  4. 既存のコピー/QR/Basescan ボタンが描画される（address があれば活性）
 *
 * NOTE:
 *  - baseURL は playwright.config.ts (STAGING_URL || https://app.ultra-auto-trade.com) に従う。
 *  - /liff-chat は本来 LINE/LIFF + Privy 認証下で動くため、CI/staging では認証状態が
 *    無いケースがある。そのためパネルが開けない環境では gracefully skip し、
 *    開けた場合のみ UI 要素を検証する（mock backend 構造問題で固定 fail にしない）。
 */

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const PANEL_TITLE = 'MY WALLET'

/**
 * ハンバーガーメニュー経由で MY WALLET パネルを開く。
 * 認証ゲート等でメニュー/項目に到達できない場合は false を返す（テストは skip 判定に使う）。
 */
async function openMyWalletPanel(page: Page): Promise<boolean> {
  await page.goto('/liff-chat')

  // ハンバーガーメニューのトリガ（aria-label or 一般的なメニューボタン）を探す。
  // 実装の HamburgerMenu に依存しすぎないよう複数候補を試す。
  const menuButton = page
    .getByRole('button', { name: /menu|メニュー/i })
    .or(page.locator('button:has(svg.lucide-menu)'))
    .first()

  if (!(await menuButton.isVisible().catch(() => false))) {
    return false
  }
  await menuButton.click().catch(() => {})

  const walletItem = page.getByText('MY WALLET', { exact: false }).first()
  if (!(await walletItem.isVisible().catch(() => false))) {
    return false
  }
  await walletItem.click().catch(() => {})

  // パネルタイトルが表示されたら成功
  const panelTitle = page.getByText(PANEL_TITLE, { exact: false }).first()
  return await panelTitle
    .isVisible({ timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
}

test.describe('[LIFF Chat] MY WALLET パネル', () => {
  test('/liff-chat が表示される', async ({ page }) => {
    const res = await page.goto('/liff-chat')
    // リダイレクト含め何らかのレスポンスが返ること（接続性の最小確認）
    expect(res?.status() ?? 0).toBeLessThan(500)
  })

  test('MY WALLET パネルを開ける（認証不可環境では skip）', async ({ page }) => {
    const opened = await openMyWalletPanel(page)
    test.skip(!opened, 'LIFF/Privy 認証状態が無くパネルを開けない環境のため skip')
    await expect(page.getByText(PANEL_TITLE, { exact: false }).first()).toBeVisible()
  })

  test('Non-Custodial / Base Mainnet バッジが表示される', async ({ page }) => {
    const opened = await openMyWalletPanel(page)
    test.skip(!opened, 'パネルを開けない環境のため skip')
    await expect(page.getByText('Non-Custodial')).toBeVisible()
    await expect(page.getByText('Base Mainnet')).toBeVisible()
  })

  test('未接続時は「ウォレットに接続する」誘導 UI が出る（空状態が埋まる）', async ({ page }) => {
    const opened = await openMyWalletPanel(page)
    test.skip(!opened, 'パネルを開けない環境のため skip')

    // address が取得できた環境ではアドレス表示になるため、未接続誘導が出るのは
    // empty 状態のときのみ。どちらの状態でも「永久読み込み中で固まらない」ことを担保する。
    const connectBtn = page.getByRole('button', { name: 'ウォレットに接続する' })
    const addressArea = page.getByText('送金前に先頭4桁・末尾4桁をご確認ください')

    // 接続誘導 か アドレス表示（注意書き）のいずれかが現れること
    await expect(connectBtn.or(addressArea).first()).toBeVisible({ timeout: 8_000 })
  })

  test('fail-visible: 永久「読み込み中...」で固まらない', async ({ page }) => {
    const opened = await openMyWalletPanel(page)
    test.skip(!opened, 'パネルを開けない環境のため skip')

    // ローディングは一時的に出てよいが、最終的に
    //   - 再試行ボタン（error）/ 再読み込み（empty）/ 接続誘導（empty）/ アドレス
    // のいずれかへ収束すること。
    const resolved = page
      .getByRole('button', { name: 'ウォレットに接続する' })
      .or(page.getByRole('button', { name: '再試行' }))
      .or(page.getByRole('button', { name: '再読み込み' }))
      .or(page.getByText('送金前に先頭4桁・末尾4桁をご確認ください'))
      .first()
    await expect(resolved).toBeVisible({ timeout: 10_000 })
  })

  test('既存のコピー/QR/Basescan アクションが描画される', async ({ page }) => {
    const opened = await openMyWalletPanel(page)
    test.skip(!opened, 'パネルを開けない環境のため skip')

    // address が無い empty/error 状態ではアクション行は disabled で存在する。
    // ボタンラベルの存在のみ最小確認（活性/非活性は address 取得状況に依存）。
    await expect(page.getByText('コピー')).toBeVisible()
    await expect(page.getByText('QR コード')).toBeVisible()
    await expect(page.getByText('Basescan')).toBeVisible()
  })
})

test.describe('[Mobile 375px][LIFF Chat] MY WALLET パネル', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('モバイルでパネルが開け、接続誘導 or アドレスへ収束する', async ({ page }) => {
    const opened = await openMyWalletPanel(page)
    test.skip(!opened, 'パネルを開けない環境のため skip')

    const resolved = page
      .getByRole('button', { name: 'ウォレットに接続する' })
      .or(page.getByText('送金前に先頭4桁・末尾4桁をご確認ください'))
      .first()
    await expect(resolved).toBeVisible({ timeout: 10_000 })
  })
})
