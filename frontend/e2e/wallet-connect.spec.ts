// Copyright (c) Ultra AutoTrade. All rights reserved.
/**
 * E2E tests for the wallet connection flow.
 *
 * Covers:
 *  1. Landing page – CTA button visibility and navigation
 *  2. /connect    – Step indicator and initial UI
 *  3. Wallet mock – Successful connection on Base Sepolia (address badge, network card)
 *  4. Wallet mock – Wrong network → Base Sepolia switch prompt
 *  5. Wallet mock – switchToBaseSepolia() → network check resolves
 *  6. Wallet mock – Connection rejection → UI unchanged
 *  7. /connect    – Minimum balance warning (always shown: current impl uses
 *                   hardcoded BigInt(0) for totalCollateralBase)
 *  8. /connect    – Terms/start-button present when network check passes
 *  9. Mobile (375 px) – Landing CTA and connect page are functional
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
// 3. ウォレット接続モック – 成功（Base Sepolia）
// ──────────────────────────────────────────────────────────────────────────────

// SKIP: connect page uses Privy (login()), not wagmi injected connector.
// window.ethereum mock does not intercept Privy's modal flow.
test.describe.skip('[Connect/Mock] 接続成功 – Base Sepolia (84532)', () => {
  test.beforeEach(async ({ page }) => {
    // Inject mock BEFORE goto so wagmi sees it on mount
    await mockEthereum(page, { chainId: 84532 })
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

  test('Base Sepolia では「接続済み」チェックマークが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(page.getByText('Base Sepolia に接続済み')).toBeVisible({ timeout: 5_000 })
  })

  test('接続後に「ウォレットを接続する」ボタンが非表示になる', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(
      page.getByRole('button', { name: /ウォレットを接続する/ })
    ).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 4. 非対応ネットワーク → 切替プロンプト
// ──────────────────────────────────────────────────────────────────────────────

// SKIP: Privy modal cannot be intercepted by window.ethereum mock.
test.describe.skip('[Connect/Mock] 非対応ネットワーク – 切替プロンプト', () => {
  test.beforeEach(async ({ page }) => {
    await mockEthereum(page, { chainId: 1 }) // Ethereum mainnet
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
  })

  test('非対応ネットワーク接続時に切替案内メッセージが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(
      page.getByText('Base Sepoliaに切り替えてください')
    ).toBeVisible({ timeout: 5_000 })
  })

  test('「Base Sepolia (テスト用) に切り替える」ボタンが表示される', async ({ page }) => {
    await clickConnectAndWait(page)
    await expect(
      page.getByRole('button', { name: 'Base Sepolia (テスト用) に切り替える' })
    ).toBeVisible({ timeout: 5_000 })
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 5. switchToBaseSepolia() – ネットワーク切替後にUIが更新される
// ──────────────────────────────────────────────────────────────────────────────

// SKIP: Privy modal cannot be intercepted by window.ethereum mock.
test.describe.skip('[Connect/Mock] switchToBaseSepolia – UI更新', () => {
  test('切替ボタンをクリックするとネットワーク確認OKになる', async ({ page }) => {
    await mockEthereum(page, { chainId: 1 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    const switchBtn = page.getByRole('button', { name: 'Base Sepolia (テスト用) に切り替える' })
    await expect(switchBtn).toBeVisible({ timeout: 5_000 })
    await switchBtn.click()

    // Mock emits 'chainChanged' → wagmi updates chainId to 84532 → re-render
    await expect(page.getByText('Base Sepolia に接続済み')).toBeVisible({
      timeout: 8_000,
    })
    await expect(switchBtn).not.toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 6. 接続拒否
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
// 7. 最低残高チェック
// ──────────────────────────────────────────────────────────────────────────────

// SKIP: beforeEach calls clickConnectAndWait which requires Privy mock (not wagmi mock).
test.describe.skip('[Connect/Mock] 最低残高チェック', () => {
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
    await mockEthereum(page, { chainId: 84532 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
    await clickConnectAndWait(page)
    // Wait for network OK before balance check card appears
    await expect(page.getByText('Base Sepolia に接続済み')).toBeVisible({
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
// 8. 規約同意セクション・開始ボタン（現実装での表示確認）
// ──────────────────────────────────────────────────────────────────────────────

// SKIP: beforeEach calls clickConnectAndWait which requires Privy mock (not wagmi mock).
test.describe.skip('[Connect] 規約同意セクション', () => {
  /**
   * allChecksPass = isConnected && isCorrectNetwork
   *
   * NOTE: 残高チェックは allChecksPass に含まれない（実装変更済み）。
   * Base Sepolia (84532) で接続すると isCorrectNetwork=true → allChecksPass=true
   * → 規約同意カードと「運用を開始する」ボタンが表示される。
   */

  test.beforeEach(async ({ page }) => {
    await mockEthereum(page, { chainId: 84532 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
    await clickConnectAndWait(page)
    await expect(page.getByText('Base Sepolia に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })

  test('ネットワーク確認OK後に「規約同意」カードが表示される', async ({
    page,
  }) => {
    // allChecksPass = isConnected && isCorrectNetwork → true
    // → 規約同意カードが表示される
    await page.waitForTimeout(500)
    const termsCard = page.locator('text=規約同意').last()
    await expect(termsCard).toBeVisible({ timeout: 5_000 })
  })

  test('ネットワーク確認OK後に「運用を開始する」ボタンが表示される', async ({
    page,
  }) => {
    // allChecksPass = isConnected && isCorrectNetwork → true
    // → 運用を開始するボタンが表示される（残高不足でも disabled 状態で表示）
    await page.waitForTimeout(500)
    await expect(
      page.getByRole('button', { name: /運用を開始する/ })
    ).toBeVisible({ timeout: 5_000 })
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 9. モバイルビューポート (375 px)
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
    test.skip(true, 'SKIP: Privy modal cannot be intercepted by window.ethereum mock.')
    await mockEthereum(page, { chainId: 84532 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    await expect(page.getByText(MOCK_ADDRESS_SHORT)).toBeVisible()
    await expect(page.getByText('Base Sepolia に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })

  test('モバイルで非対応ネットワーク接続時に切替プロンプトが表示される', async ({
    page,
  }) => {
    test.skip(true, 'SKIP: Privy modal cannot be intercepted by window.ethereum mock.')
    await mockEthereum(page, { chainId: 1 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()

    await clickConnectAndWait(page)
    // connect ページの非対応ネットワーク時の案内テキスト（実装ソースより）
    await expect(
      page.getByText('Base Sepoliaに切り替えてください')
    ).toBeVisible({ timeout: 5_000 })
    await expect(
      page.getByRole('button', { name: 'Base Sepolia (テスト用) に切り替える' })
    ).toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 10. 運用モード選択UI (allChecksPass 時のみ表示)
// ──────────────────────────────────────────────────────────────────────────────

// SKIP: beforeEach calls clickConnectAndWait which requires Privy mock (not wagmi mock).
test.describe.skip('[Connect] 運用モード選択UI', () => {
  /**
   * NOTE: allChecksPass = isConnected && isCorrectNetwork
   * The mode selector is rendered only when allChecksPass is true.
   * These tests use Base Sepolia (84532) mock so the network check passes.
   *
   * Because balanceCheck is always isBelowMinimum=true (mock data), the
   * balance card shows a warning, but allChecksPass is NOT gated on balance —
   * it only requires isConnected && isCorrectNetwork. Therefore the mode
   * selector IS rendered after a successful connection on a correct network.
   *
   * SKIP理由: 運用モード選択UIはソースコードに実装済み（allChecksPass && <Card>運用モード選択）だが、
   * テスト対象の staging サーバー（77.42.46.155:3000）のビルドに未反映のため失敗する。
   * staging デプロイ後に skip を解除すること。
   */

  test.beforeEach(async ({ page }) => {
    // Clear ultra_user_mode to ensure default state
    await page.addInitScript(() => {
      localStorage.removeItem('ultra_user_mode')
    })
    await mockEthereum(page, { chainId: 84532 })
    await page.goto('/connect')
    await clearWagmiStorage(page)
    await page.reload()
    await clickConnectAndWait(page)
    await expect(page.getByText('Base Sepolia に接続済み')).toBeVisible({
      timeout: 5_000,
    })
  })

  test('connect ページにモード選択UIが表示される', async ({ page }) => {
    test.skip(true, '理由: 運用モード選択UIがステージングサーバーのビルドに未反映。staging デプロイ後に解除すること。')
    await expect(page.getByText('運用モード選択')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('フルオート')).toBeVisible()
    await expect(page.getByText('セミオート')).toBeVisible()
    await expect(page.getByText('マニュアル')).toBeVisible()
  })

  test('デフォルトは managed（フルオート）', async ({ page }) => {
    test.skip(true, '理由: 運用モード選択UIがステージングサーバーのビルドに未反映。staging デプロイ後に解除すること。')
    // The managed button should have the active ring class (ring-green-500)
    // We verify by checking that the フルオート button has a ring style applied
    const managedBtn = page.locator('[data-mode="managed"]')
    await expect(managedBtn).toBeVisible({ timeout: 5_000 })
    await expect(managedBtn).toHaveClass(/ring-green-500/)
  })

  test('モード選択がlocalStorageに保存される', async ({ page }) => {
    test.skip(true, '理由: 運用モード選択UIがステージングサーバーのビルドに未反映。staging デプロイ後に解除すること。')
    // Click the セミオート (active) button
    const activeBtn = page.locator('[data-mode="active"]')
    await expect(activeBtn).toBeVisible({ timeout: 5_000 })
    await activeBtn.click()

    // Verify localStorage was updated
    const stored = await page.evaluate(() => localStorage.getItem('ultra_user_mode'))
    expect(stored).toBe('active')

    // Verify the active button now has the ring style
    await expect(activeBtn).toHaveClass(/ring-yellow-500/)
  })
})
