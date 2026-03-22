// Copyright (c) Ultra AutoTrade. All rights reserved.
/**
 * E2E tests for the wallet connection flow.
 *
 * Covers:
 *  1. Landing page – CTA button visibility and navigation
 *  2. /connect    – Step indicator and initial UI
 *  3. Wallet mock – Successful connection (address badge, network card)
 *  4. Wallet mock – Wrong network → Arbitrum switch prompt
 *  5. Wallet mock – switchToArbitrum() → network check resolves
 *  6. Wallet mock – Arbitrum Sepolia (421614) accepted as correct network
 *  7. Wallet mock – Connection rejection → UI unchanged
 *  8. /connect    – Minimum balance warning (always shown: current impl uses
 *                   hardcoded BigInt(0) for totalCollateralBase)
 *  9. /connect    – Terms/start-button absent when balance check fails
 * 10. Mobile (375 px) – Landing CTA and connect page are functional
 */

import { test, expect } from '@playwright/test'
import {
  mockEthereum,
  MOCK_ADDRESS_SHORT,
} from './helpers/wallet-mock'

// ──────────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────────

/** Clear wagmi's persisted connection state so each test starts fresh. */
async function clearWagmiStorage(page: import('@playwright/test').Page) {
  await page.evaluate(() => {
    Object.keys(localStorage).forEach((key) => {
      if (key.startsWith('wagmi') || key.startsWith('wc@')) {
        localStorage.removeItem(key)
      }
    })
  })
}

/** Click the wallet connect button and wait for wagmi to process the response. */
async function clickConnectAndWait(page: import('@playwright/test').Page) {
  const btn = page.getByRole('button', { name: /ウォレットを接続する/ })
  await expect(btn).toBeVisible()
  await btn.click()
  // wagmi processes eth_requestAccounts asynchronously; wait for the address
  // badge that appears only after isConnected becomes true
  await expect(page.getByText('接続済み:')).toBeVisible({ timeout: 8_000 })
}

// ──────────────────────────────────────────────────────────────────────────────
// 1. Landing page
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Landing] CTAボタン', () => {
  test('ヒーローセクションにCTAボタンが表示される', async ({ page }) => {
    await page.goto('/')
    // The hero section link button text
    const cta = page.getByRole('link', { name: 'ウォレットを接続する' }).first()
    await expect(cta).toBeVisible()
  })

  test('CTAボタンをクリックすると /connect に遷移する', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'ウォレットを接続する' }).first().click()
    await expect(page).toHaveURL(/\/connect/)
    await expect(page.getByRole('heading', { name: 'ウォレットを接続' })).toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 2. /connect 初期状態
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect] 初期状態', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/connect')
    await clearWagmiStorage(page)
  })

  test('3ステップインジケーターが全て表示される', async ({ page }) => {
    await expect(page.getByText('ウォレット接続').first()).toBeVisible()
    await expect(page.getByText('ネットワーク確認')).toBeVisible()
    await expect(page.getByText('規約同意')).toBeVisible()
  })

  test('「ウォレットを接続する」ボタンが表示される', async ({ page }) => {
    const btn = page.getByRole('button', { name: /ウォレットを接続する/ })
    await expect(btn).toBeVisible()
  })

  test('未接続時はアドレスバッジが表示されない', async ({ page }) => {
    await expect(page.getByText('接続済み:')).not.toBeVisible()
  })

  test('未接続時はネットワーク確認カードが表示されない', async ({ page }) => {
    await expect(page.getByText('ネットワーク確認', { exact: true }).nth(1)).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 3. ウォレット接続モック – 成功（Arbitrum One）
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect/Mock] 接続成功 – Arbitrum One (42161)', () => {
  test.beforeEach(async ({ page }) => {
    // Inject mock BEFORE goto so wagmi sees it on mount
    await mockEthereum(page, { chainId: 42161 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    // Reload so wagmi re-initialises with cleared storage
    await page.reload()
  })

  test('接続後にアドレスバッジが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(page.getByText(MOCK_ADDRESS_SHORT)).toBeVisible()
  })

  test('接続後にネットワーク確認カードが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(page.getByText('ネットワーク確認').nth(1)).toBeVisible({ timeout: 5_000 })
  })

  test('Arbitrum One では「接続済み」チェックマークが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(page.getByText('Arbitrum One に接続済み')).toBeVisible({ timeout: 5_000 })
  })

  test('接続後に「ウォレットを接続する」ボタンが非表示になる', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(
      page.getByRole('button', { name: /ウォレットを接続する/ })
    ).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 4. 非Arbitrumネットワーク → 切替プロンプト
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect/Mock] 非Arbitrumネットワーク – 切替プロンプト', () => {
  test.beforeEach(async ({ page }) => {
    await mockEthereum(page, { chainId: 1 }) // Ethereum mainnet
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
  })

  test('非Arbitrum接続時に切替案内メッセージが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(
      page.getByText('Arbitrum Oneネットワークに切り替えてください')
    ).toBeVisible({ timeout: 5_000 })
  })

  test('「Arbitrum One に切り替える」ボタンが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(
      page.getByRole('button', { name: 'Arbitrum One に切り替える' })
    ).toBeVisible({ timeout: 5_000 })
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 5. switchToArbitrum() – ネットワーク切替後にUIが更新される
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect/Mock] switchToArbitrum – UI更新', () => {
  test('切替ボタンをクリックするとネットワーク確認OKになる', async ({ page }) => {
    await mockEthereum(page, { chainId: 1 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    const switchBtn = page.getByRole('button', { name: 'Arbitrum One に切り替える' })
    await expect(switchBtn).toBeVisible({ timeout: 5_000 })
    await switchBtn.click()

    // Mock emits 'chainChanged' → wagmi updates chainId to 42161 → re-render
    await expect(page.getByText('Arbitrum One に接続済み')).toBeVisible({
      timeout: 8_000,
    })
    await expect(switchBtn).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 6. Arbitrum Sepolia (421614) でも正常ネットワークと認識される
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect/Mock] Arbitrum Sepolia (421614)', () => {
  test('Arbitrum Sepolia でもネットワーク確認OKになる', async ({ page }) => {
    await mockEthereum(page, { chainId: 421614 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    await expect(page.getByText('Arbitrum One に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 7. 接続拒否
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect/Mock] 接続拒否', () => {
  test('ユーザーが接続を拒否してもUIは初期状態を保つ', async ({ page }) => {
    await mockEthereum(page, { rejectConnect: true })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    const connectBtn = page.getByRole('button', { name: /ウォレットを接続する/ })
    await expect(connectBtn).toBeVisible()
    await connectBtn.click()

    // wagmi receives a rejection; isConnected stays false
    // Give it a moment to settle, then verify nothing connected
    await page.waitForTimeout(1_500)
    await expect(page.getByText('接続済み:')).not.toBeVisible()
    // Connect button should still be present (or the page still shows step 1)
    // wagmi may hide/disable the button briefly; check address badge absence is key
    await expect(page.getByText(MOCK_ADDRESS_SHORT)).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 8. 最低残高チェック
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect/Mock] 最低残高チェック', () => {
  /**
   * NOTE: The connect page hardcodes `totalCollateralBase: BigInt(0)` in
   * mockAccountData, so checkMinimum() always returns isBelowMinimum=true.
   * These tests therefore validate the "below minimum" branch.
   *
   * The "residual >= $3,000 → no warning" branch requires real Aave account
   * data integration and cannot be reached through the current UI without
   * modifying production code.
   */

  test.beforeEach(async ({ page }) => {
    await mockEthereum(page, { chainId: 42161 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
    await clickConnectAndWait(page)
    // Wait for network OK before balance check card appears
    await expect(page.getByText('Arbitrum One に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })

  test('最低残高確認カードが表示される', async ({ page }) => {
    await expect(page.getByText('最低残高確認')).toBeVisible({ timeout: 5_000 })
  })

  test('$3,000未満の警告メッセージが表示される（現実装では常にこの状態）', async ({
    page,
  }) => {
    // checkMinimum({totalCollateralBase: BigInt(0)}) → isBelowMinimum: true
    await expect(
      page.getByText(/最低運用額.*\$3,000.*USD.*を下回っています/)
    ).toBeVisible({ timeout: 5_000 })
  })

  test('最低運用額の表示に $3,000 が含まれる', async ({ page }) => {
    await expect(page.getByText(/最低運用額: \$3,000 USD/)).toBeVisible({
      timeout: 5_000,
    })
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 9. 規約同意セクション・開始ボタン（現実装での非表示確認）
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Connect] 規約同意セクション', () => {
  /**
   * allChecksPass = isConnected && isCorrectNetwork && !balanceCheck.isBelowMinimum
   *
   * Because isBelowMinimum is always true (see mockAccountData above),
   * allChecksPass is always false, so the terms checkboxes and the
   * "運用を開始する" button are never rendered.
   *
   * These tests document that expected behaviour and will need to be
   * updated once real Aave data integration lands.
   */

  test.beforeEach(async ({ page }) => {
    await mockEthereum(page, { chainId: 42161 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
    await clickConnectAndWait(page)
    await expect(page.getByText('Arbitrum One に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })

  test('残高不足のため「規約同意」カードは表示されない（現実装）', async ({
    page,
  }) => {
    // Give the page time to settle after the balance card appears
    await page.waitForTimeout(500)
    const termsCard = page.locator('text=規約同意').last()
    await expect(termsCard).not.toBeVisible()
  })

  test('残高不足のため「運用を開始する」ボタンは表示されない（現実装）', async ({
    page,
  }) => {
    await page.waitForTimeout(500)
    await expect(
      page.getByRole('button', { name: /運用を開始する/ })
    ).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 10. モバイルビューポート (375 px)
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[Mobile 375px] 基本フロー', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('ランディングページのCTAボタンがモバイルで表示される', async ({ page }) => {
    await page.goto('/')
    const cta = page.getByRole('link', { name: 'ウォレットを接続する' }).first()
    await expect(cta).toBeVisible()
  })

  test('/connect の3ステップインジケーターがモバイルで表示される', async ({
    page,
  }) => {
    await page.goto('/connect')
    await expect(page.getByText('ウォレット接続').first()).toBeVisible()
    await expect(page.getByText('ネットワーク確認')).toBeVisible()
    await expect(page.getByText('規約同意')).toBeVisible()
  })

  test('モバイルでウォレット接続→アドレスバッジが表示される', async ({ page }) => {
    await mockEthereum(page, { chainId: 42161 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    await expect(page.getByText(MOCK_ADDRESS_SHORT)).toBeVisible()
    await expect(page.getByText('Arbitrum One に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })

  test('モバイルで非Arbitrum接続時に切替プロンプトが表示される', async ({
    page,
  }) => {
    await mockEthereum(page, { chainId: 1 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    await expect(
      page.getByText('Arbitrum Oneネットワークに切り替えてください')
    ).toBeVisible({ timeout: 5_000 })
    await expect(
      page.getByRole('button', { name: 'Arbitrum One に切り替える' })
    ).toBeVisible()
  })
})
