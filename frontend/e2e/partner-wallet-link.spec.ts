// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [F-17 L5] Partner wallet link E2E — Gate 4 verification.
//
// 検証範囲:
//   WalletConnectCard の API 呼出契約 + レスポンスハンドリング (UI 状態遷移)
//
// 方式: storageState (.auth/partner.json) 流用 + page.route で POST /auth/wallet/link 傍受
//   - partner.json から JWT を読み取り addInitScript で localStorage に注入
//   - /auth/me を page.route でモック → PartnerGuard を通過
//   - POST /auth/wallet/link を page.route で傍受して各レスポンスを制御
//
// スコープ外 (別タスク #8 "Privy test token integration"):
//   - Privy 署名モーダル自体の操作
//   - 実際の署名生成フロー
//   - wallet-connect.spec.ts の SKIP 群の昇格
//
// スクリーンショット: e2e/screenshots/f17-*

import { test, expect, Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { signWalletLinkPayload, getTestAccount } from './fixtures/privy'

// ─── 定数 ─────────────────────────────────────────────────────────────────────

const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'f17')

const MOCK_WALLET_RESPONSE = {
  wallet_address: '0xABCD1234567890ABCD1234',
  network: 'Base Sepolia',
}

const PARTNER_MOCK_USER = {
  id: 15,
  email: 'partner-e2e@ultra-autotrade.com',
  username: 'partner-e2e',
  role: 'partner',
  is_active: true,
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  terms_accepted_at: null,
  terms_version: null,
  risk_mode: 'conservative',
  invited_by: null,
  tier: 'GENERAL',
  risk_mode_label: 'ローリスク',
}

// ─── ヘルパー ─────────────────────────────────────────────────────────────────

function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
  }
}

async function saveScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: true,
  })
}

/** partner.json を読んで JWT + expiresAt を返す。ファイルがなければ undefined。 */
function readPartnerAuth(): { token: string; expiresAt: number } | undefined {
  const authPath = path.join('e2e', '.auth', 'partner.json')
  if (!fs.existsSync(authPath)) return undefined
  const raw = JSON.parse(fs.readFileSync(authPath, 'utf-8')) as {
    token: string
    expiresAt: number
    email?: string
  }
  return raw
}

/**
 * partner JWT を localStorage に注入 + /auth/me をモック。
 * PartnerGuard が /login にリダイレクトしないための最小セットアップ。
 * contract test (TC1-TC4) は /auth/wallet/link レスポンス制御が目的のため
 * /auth/me はモックのまま維持する (CF Access 保護下の staging-new で安定実行するため)。
 */
async function setupPartnerAuth(page: Page): Promise<void> {
  const auth = readPartnerAuth()
  const token = auth?.token ?? 'dummy-partner-token-for-e2e'
  const safeExpiresAt = Math.max(
    auth?.expiresAt ?? 0,
    Date.now() + 24 * 60 * 60 * 1000,
  )

  await page.addInitScript(
    (args) => {
      localStorage.setItem(args.tokenKey, args.t)
      localStorage.setItem(args.expiresKey, String(args.e))
    },
    {
      tokenKey: 'ultra_auth_token',
      expiresKey: 'ultra_auth_expires',
      t: token,
      e: safeExpiresAt,
    },
  )

  await page.route('**/auth/me', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(PARTNER_MOCK_USER),
      })
    } else {
      await route.continue()
    }
  })

  // ExecutionModeCard が GET /api/user/settings を呼ぶのでモック
  await page.route('**/api/user/settings', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user_mode: 'managed', execution_policy: 'conservative' }),
      })
    } else {
      await route.continue()
    }
  })
}

// ─── テスト ──────────────────────────────────────────────────────────────────

test.describe('[F-17] partner wallet link flow', () => {
  test.beforeEach(ensureScreenshotDir)

  // ── TC1: 未接続 UI ──────────────────────────────────────────────────────────
  test('TC1: /partner/settings に WalletConnectCard「未接続」UI が表示される', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await page.goto('/partner/settings')
    await page.waitForLoadState('domcontentloaded')

    // PartnerGuard がリダイレクトしていないことを確認
    const url = page.url()
    expect(url).toContain('/partner/settings')

    // WalletConnectCard の「ウォレット接続」ボタンが表示されること
    const connectBtn = page.getByRole('button', { name: 'ウォレット接続' })
    await expect(connectBtn).toBeVisible({ timeout: 10_000 })

    // 未接続テキストが表示されること
    await expect(page.getByText('ウォレット未接続')).toBeVisible()

    await saveScreenshot(page, 'tc1-wallet-unlinked')
  })

  // ── TC2: 200 → 接続済 UI ────────────────────────────────────────────────────
  // SKIP: 2026-05-12 hotfix で WalletConnectCard が空の POST から
  // Privy modal → 実署名 → POST {address,signature,message} へ変更された。
  // page.route() 直前のボタンクリックだけでは POST が発火しなくなったため、本ケースは
  // wallet-connect-link.spec.ts の Privy-aware ケースに移譲。
  test.skip('TC2: POST /auth/wallet/link 200 → 接続済 UI + アドレス + ネットワーク表示', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    await page.route('**/auth/wallet/link', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_WALLET_RESPONSE),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/settings')
    await page.waitForLoadState('domcontentloaded')

    const connectBtn = page.getByRole('button', { name: 'ウォレット接続' })
    await expect(connectBtn).toBeVisible({ timeout: 10_000 })
    await connectBtn.click()

    // 接続済み表示に切り替わること
    await expect(page.getByText('接続済み:')).toBeVisible({ timeout: 8_000 })

    // アドレスが truncate されて表示されること (0xABCD...1234)
    await expect(page.getByText('0xABCD...1234')).toBeVisible()

    // ネットワークバッジ (Base Sepolia) が表示されること
    await expect(page.getByText('Base Sepolia')).toBeVisible()

    await saveScreenshot(page, 'tc2-wallet-linked-200')
  })

  // ── TC3: 409 → toast エラー ─────────────────────────────────────────────────
  // SKIP: 2026-05-12 hotfix で実署名フローに変更。TC2 と同じ理由で route mock 単独
  // ではテストできない。エラー toast 表示は wallet-connect-link.spec.ts で再現。
  test.skip('TC3: POST /auth/wallet/link 409 → toast "このウォレットは別アカウントで登録済みです"', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    await page.route('**/auth/wallet/link', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'wallet already linked to another account' }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/settings')
    await page.waitForLoadState('domcontentloaded')

    const connectBtn = page.getByRole('button', { name: 'ウォレット接続' })
    await expect(connectBtn).toBeVisible({ timeout: 10_000 })
    await connectBtn.click()

    // toast エラーメッセージが表示されること
    await expect(
      page.getByText('このウォレットは別アカウントで登録済みです'),
    ).toBeVisible({ timeout: 8_000 })

    // ボタンは引き続き表示されること (接続済 UI に切り替わらない)
    await expect(page.getByRole('button', { name: 'ウォレット接続' })).toBeVisible()

    await saveScreenshot(page, 'tc3-wallet-409-duplicate')
  })

  // ── TC4: 422 → toast エラー ─────────────────────────────────────────────────
  // SKIP: 2026-05-12 hotfix で実署名フローに変更。
  test.skip('TC4: POST /auth/wallet/link 422 → toast "署名検証に失敗しました"', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    await page.route('**/auth/wallet/link', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'signature verification failed' }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/settings')
    await page.waitForLoadState('domcontentloaded')

    const connectBtn = page.getByRole('button', { name: 'ウォレット接続' })
    await expect(connectBtn).toBeVisible({ timeout: 10_000 })
    await connectBtn.click()

    // toast エラーメッセージが表示されること
    await expect(
      page.getByText('署名検証に失敗しました'),
    ).toBeVisible({ timeout: 8_000 })

    // ボタンは引き続き表示されること
    await expect(page.getByRole('button', { name: 'ウォレット接続' })).toBeVisible()

    await saveScreenshot(page, 'tc4-wallet-422-sig-fail')
  })
})

// ─── Lane G: 実 backend 疎通確認 ─────────────────────────────────────────────
// mock なし。partner JWT で実 staging-new backend を叩く。
// PR #207 稼働確認 (endpoint 存在 + 422 返却) に特化。

test.describe('[F-17 Lane G] /auth/wallet/link 実 backend 疎通', () => {
  test('TC-G2: POST /auth/wallet/link 無効署名 → 422 (PR #207 staging-new 稼働確認)', async ({
    request,
  }) => {
    const auth = readPartnerAuth()
    test.skip(!auth, 'partner.json なし — E2E_PARTNER_EMAIL / PASSWORD を設定して再実行')

    const backendUrl =
      process.env.NEXT_PUBLIC_API_URL ?? 'https://api.ultra-auto-trade.com'

    const resp = await request.post(`${backendUrl}/auth/wallet/link`, {
      headers: {
        Authorization: `Bearer ${auth!.token}`,
        'Content-Type': 'application/json',
      },
      data: {
        address: '0xABCD1234567890ABcD1234567890aBcD12345678',
        signature: '0xe2e_test_invalid_signature_lane_g',
        message: 'sign this: e2e test 2026-01-01T00:00:00Z',
      },
    })

    // 404 なら endpoint 未デプロイ、422 なら署名検証まで到達 (正常動作)
    expect(resp.status()).toBe(422)
  })
})

// ─── F-17/8: 実 viem 署名で /auth/wallet/link 200 path ─────────────────────
// Lane G TC-G2 (無効署名 → 422) の続編。viem の EIP-191 personal_sign で
// 復元可能な署名を生成し、200 + DB users.wallet_address 反映まで実環境で検証する。
// idempotent: 同一 JWT user × 同一 wallet なので再リンク = 200 (副作用なし)。

test.describe('[F-17/8] /auth/wallet/link 200 — real viem signature', () => {
  test('TC-G5: viem 署名 → 200 + GET /auth/me.wallet_address 反映', async ({
    request,
  }) => {
    const auth = readPartnerAuth()
    test.skip(!auth, 'partner.json なし — E2E_PARTNER_EMAIL / PASSWORD を設定して再実行')

    const backendUrl =
      process.env.NEXT_PUBLIC_API_URL ?? 'https://api.ultra-auto-trade.com'

    const payload = await signWalletLinkPayload()
    const expectedAddress = getTestAccount().address.toLowerCase()

    // 1. POST /auth/wallet/link → 200
    const linkResp = await request.post(`${backendUrl}/auth/wallet/link`, {
      headers: {
        Authorization: `Bearer ${auth!.token}`,
        'Content-Type': 'application/json',
      },
      data: payload,
    })

    // 409 (別 user に既にリンク済) は staging-new の汚染を示す。明示メッセージで失敗。
    if (linkResp.status() === 409) {
      throw new Error(
        `409: ${expectedAddress} が partner test user 以外にリンク済。` +
          'staging-new で UPDATE users SET wallet_address=NULL WHERE id != <partner_id> を実行のこと。',
      )
    }
    expect(linkResp.status(), `link response: ${await linkResp.text()}`).toBe(200)

    const linkBody = (await linkResp.json()) as {
      user_id: number
      wallet_address: string
      linked_at: string
    }
    expect(linkBody.wallet_address).toBe(expectedAddress)
    expect(linkBody.linked_at).toMatch(/T.*\d/)

    // 2. GET /auth/me → wallet_address が反映されている
    const meResp = await request.get(`${backendUrl}/auth/me`, {
      headers: { Authorization: `Bearer ${auth!.token}` },
    })
    expect(meResp.status()).toBe(200)
    const meBody = (await meResp.json()) as { wallet_address?: string | null }
    expect(meBody.wallet_address).toBe(expectedAddress)
  })
})
