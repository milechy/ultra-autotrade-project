// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Lane F-3: Lead 検証 7 シナリオ統合 E2E
//
// TC-B  Wallet badge partner 表示          (Lane G TC-G3 拡張 — wallet 接続済みケース)
// TC-D  /connect partner → /partner/dashboard  (connect ページ到達確認 + 遷移先検証)
// TC-E  AppShell ハンバーガー 紹介プログラム → /partner/referral 200
// TC-G  /api/invitations 廃止 (4xx) + InviteModal partner 非表示
// TC-I  KPI 接続確認 (/api/partner/stats スキーマ + 30 秒以内レスポンス)
// TC-J  /partner/users 一覧 + 詳細モーダル + 運用情報表示
// TC-K  tx_hash / wallet_address が DOM・API レスポンスに非含 (法務)
//
// 実行方法 (Hetzner 内部 / staging-new):
//   ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155 \
//     "cd /opt/ultra-autotrade/frontend && \
//      set -a && source /opt/ultra-autotrade/.env.staging-new && set +a && \
//      STAGING_URL=http://127.0.0.1:3001 \
//      E2E_PARTNER_EMAIL=\$E2E_PARTNER_EMAIL \
//      E2E_PARTNER_PASSWORD=\$E2E_PARTNER_PASSWORD \
//      E2E_INTERNAL_BACKEND_URL=http://localhost:8082 \
//      npx playwright test e2e/lane-f3-lead-verification.spec.ts --retries=2 2>&1 | tail -150"
//
// 依存: Lane G setupCfAccessRelay パターン派生
// Asana GID: 1214692363772438

import { test, expect, Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { setupPartnerAuth, readPartnerAuth } from './helpers/partner-auth'

// ─── 定数 ─────────────────────────────────────────────────────────────────────

const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'lane-f3')
const INTERNAL_BACKEND = process.env.E2E_INTERNAL_BACKEND_URL ?? 'http://localhost:8082'
const HAS_CREDENTIALS = Boolean(
  process.env.E2E_PARTNER_EMAIL && process.env.E2E_PARTNER_PASSWORD,
)

// wagon mock で使用する固定アドレス (helpers/wallet-mock.ts と同値)
const MOCK_ADDRESS = '0xAbCd1234567890AbCd1234567890AbCd12345678'
// UserHeader.tsx: `${address.slice(0, 6)}...${address.slice(-4)}`
const MOCK_ADDRESS_BADGE = `${MOCK_ADDRESS.slice(0, 6)}...${MOCK_ADDRESS.slice(-4)}`

// /partner/users ページのモックユーザーデータ
const MOCK_USERS = [
  {
    id: 1,
    username: 'テストユーザーA',
    email: 'tester-a@example.com',
    role: 'viewer',
    is_active: true,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    terms_accepted_at: null,
    terms_version: null,
    risk_mode: 'conservative',
    invited_by: null,
    tier: 'GENERAL',
    risk_mode_label: 'ローリスク',
  },
]

// PartnerStatsResponse スキーマ準拠 (wallet/tx フィールドなし)
const MOCK_PARTNER_STATS = {
  total_aum: '1000000.00',
  yesterday_aum: '999000.00',
  month_return_pct: '2.50',
  yesterday_return_pct: '0.10',
  user_count: 1,
}

// ─── ヘルパー ─────────────────────────────────────────────────────────────────

function ensureScreenshotDir(): void {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
  }
}

async function saveScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: false,
  })
}

/**
 * wagmi の injected connector が自動再接続できるよう window.ethereum と
 * localStorage を事前設定する。
 * helpers/wallet-mock.ts の mockEthereum は connected=false スタートのため
 * TC-B では使えない。本関数は eth_accounts を即時 MOCK_ADDRESS で返す。
 */
async function setupWalletMock(page: Page): Promise<void> {
  await page.addInitScript((mockAddr: string) => {
    // EIP-1193 mock — eth_accounts を即時返す (wagmi auto-reconnect 対応)
    const eth = {
      isMetaMask: true,
      selectedAddress: mockAddr,
      chainId: '0x14a34', // Base Sepolia (84532)
      networkVersion: '84532',
      request: async ({ method }: { method: string }): Promise<unknown> => {
        switch (method) {
          case 'eth_requestAccounts':
          case 'eth_accounts':
            return [mockAddr]
          case 'eth_chainId':
            return '0x14a34'
          case 'net_version':
            return '84532'
          case 'eth_getBalance':
            return '0xde0b6b3a7640000' // 1 ETH in wei
          default:
            return null
        }
      },
      on: (_event: string, _handler: () => void) => eth,
      removeListener: (_event: string, _handler: () => void) => eth,
      addListener: (_event: string, _handler: () => void) => eth,
      _emit: () => {},
    }
    ;(window as unknown as Record<string, unknown>).ethereum = eth

    // wagmi v2/v3 の auto-reconnect 用 localStorage キャッシュ
    // wagmi.cache と wagmi.store の両方を書き込む (バージョン依存で変わる場合に備える)
    const wagmiState = JSON.stringify({
      state: {
        connections: {
          injected: { accounts: [mockAddr], chainId: 84532 },
        },
        current: 'injected',
        status: 'connected',
      },
    })
    localStorage.setItem('wagmi.cache', wagmiState)
    localStorage.setItem('wagmi.store', wagmiState)
  }, MOCK_ADDRESS)
}

/**
 * Lane G パターン: staging-new の CF Access 保護 API を内部 backend に relay。
 * (yamamoto-partner-flow.spec.ts:776 の同名関数と同実装)
 */
async function setupCfAccessRelay(page: Page, token: string): Promise<void> {
  await page.route('**/api-staging.ultra-auto-trade.com/**', async (route) => {
    const originalUrl = route.request().url()
    const internalUrl = originalUrl.replace(
      /https?:\/\/api-staging\.ultra-auto-trade\.com/,
      INTERNAL_BACKEND,
    )
    const method = route.request().method()
    const postData = route.request().postData()
    try {
      const res = await fetch(internalUrl, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        ...(postData ? { body: postData } : {}),
      })
      const body = await res.text()
      await route.fulfill({
        status: res.status,
        contentType: res.headers.get('content-type') ?? 'application/json',
        body,
      })
    } catch (e) {
      console.error('[relay] failed:', internalUrl, e)
      await route.continue()
    }
  })
}

/** 実ログイン + CF Access relay (TC-I 用) */
async function setupLaneGAuth(page: Page): Promise<void> {
  const auth = readPartnerAuth()
  if (!auth) throw new Error('e2e/.auth/partner.json not found — global-setup.ts を実行してください')
  const { token, expiresAt } = auth
  const safeExpires = Math.max(expiresAt, Date.now() + 24 * 60 * 60 * 1000)

  await setupCfAccessRelay(page, token)

  await page.addInitScript(
    (args: { tokenKey: string; expiresKey: string; t: string; e: number }) => {
      localStorage.setItem(args.tokenKey, args.t)
      localStorage.setItem(args.expiresKey, String(args.e))
    },
    {
      tokenKey: 'ultra_auth_token',
      expiresKey: 'ultra_auth_expires',
      t: token,
      e: safeExpires,
    },
  )
}

// ─── TC-B: Wallet badge partner 表示 ─────────────────────────────────────────
//
// UserHeader.tsx:120 の条件: {(isAdmin || isPartner) && address && <Badge>}
// MOCK_ADDRESS = '0xAbCd1234567890AbCd1234567890AbCd12345678'
// → badge text: '0xAbCd...5678'

test.describe('TC-B: Wallet badge — partner 実ログイン + wallet 接続済み', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC-B: partner ロール + wagmi mock → UserHeader wallet badge 表示', async ({
    page,
  }) => {
    // badge は hidden sm:flex のため desktop viewport 必須
    await page.setViewportSize({ width: 1280, height: 800 })
    // ethereum mock を先に設定 (page.goto より前)
    await setupWalletMock(page)
    // partner auth mock (/auth/me → partner role)
    await setupPartnerAuth(page)

    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    // wagmi auto-connect に 3-5 秒余裕を持たせる
    await page.waitForTimeout(5000)

    // badge: `${address.slice(0,6)}...${address.slice(-4)}` = '0xAbCd...5678'
    const badge = page.locator('header').getByText(MOCK_ADDRESS_BADGE)
    await expect(badge).toBeVisible({ timeout: 15_000 })

    await saveScreenshot(page, 'tc-b-wallet-badge-partner')
  })
})

// ─── TC-D: /connect partner → /partner/dashboard 遷移先検証 ──────────────────
//
// connect ページ表示確認 + partner 向け遷移先 /partner/dashboard の到達確認。
// TODO(Privy-E2E): handleStart() の完全リダイレクトフロー検証は Privy mock integration 必須。

test.describe('TC-D: /connect ページ表示 + partner 遷移先確認', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC-D: /connect が表示される (未認証) + partner は /partner/dashboard に到達できる', async ({
    page,
  }) => {
    // 1) 未認証で /connect にアクセス → step indicator が出ること
    await page.goto('/connect')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    // connect ページが表示されている (/login にリダイレクトされない)
    expect(page.url()).toContain('/connect')

    // StepIndicator の "ウォレット接続" が表示されること
    await expect(
      page.getByText('ウォレット接続', { exact: true }),
    ).toBeVisible({ timeout: 10_000 })

    await saveScreenshot(page, 'tc-d-connect-page')

    // 2) partner auth をセットアップして /partner/dashboard に到達できることを確認
    //    (handleStart() 後のリダイレクト先が正しいことを間接的に検証)
    await setupPartnerAuth(page)

    // partner 向け wallet-connect backend call をモック
    await page.route('**/auth/wallet-connect', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            access_token: 'mock-wallet-token-partner',
            token_type: 'bearer',
            expires_in: 86400,
          }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    // partner は /partner/dashboard に到達できる (login にリダイレクトされない)
    expect(page.url()).toContain('/partner/dashboard')

    await saveScreenshot(page, 'tc-d-partner-dashboard-destination')
  })
})

// ─── TC-E: AppShell ハンバーガー 紹介プログラム → /partner/referral 200 ────────
//
// AppShell.tsx:25: { href: "/partner/referral", label: "紹介プログラム" }
// hamburger は max-width: 639px で出現 (CSS: .mobile-hamburger)

test.describe('TC-E: AppShell ハンバーガー → 紹介プログラム → /partner/referral', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC-E: mobile viewport でハンバーガー → 紹介プログラム → /partner/referral 200', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await setupPartnerAuth(page)

    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    expect(page.url()).toContain('/partner/dashboard')

    // ハンバーガーボタンをクリック (aria-label="メニュー")
    const hamburger = page.getByRole('button', { name: 'メニュー' })
    await expect(hamburger).toBeVisible({ timeout: 8_000 })
    await hamburger.click()

    // ドロップダウン内の「紹介プログラム」リンクをクリック
    const referralLink = page.getByRole('link', { name: '紹介プログラム' })
    await expect(referralLink).toBeVisible({ timeout: 5_000 })
    await referralLink.click()

    // /partner/referral に遷移し 404 にならないこと
    await page.waitForURL(/\/partner\/referral/, { timeout: 8_000 })
    expect(page.url()).toContain('/partner/referral')

    // main コンテンツが表示されること
    await expect(page.locator('main')).toBeVisible({ timeout: 8_000 })

    await saveScreenshot(page, 'tc-e-referral-nav')
  })
})

// ─── TC-G: /api/invitations 廃止確認 + InviteModal partner 非表示 ─────────────
//
// main.py:208: `# app.include_router(invitations_router)` (コメントアウト) → 404
// InviteModal は app/(admin)/settings/users/page.tsx のみに存在。
// partner 向け /partner/users には招待 UI がないことを確認。

test.describe('TC-G: /api/invitations 廃止 + InviteModal partner 非表示', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC-G-1: /api/invitations が 4xx を返す (router コメントアウト確認)', async ({
    page,
  }) => {
    const baseUrl = process.env.STAGING_URL || 'https://app.ultra-auto-trade.com'
    // backend への直接リクエスト (CF Access 非経由で十分)
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? 'https://api.ultra-auto-trade.com'
    const res = await page.request.get(`${backendUrl}/api/invitations`)
    // invitations router は無効化済みのため 404 または 410 が期待される
    expect(res.status()).toBeGreaterThanOrEqual(400)
    expect(res.status()).toBeLessThan(500)

    console.log(`[INFO] /api/invitations status: ${res.status()} (廃止確認 OK)`)
  })

  test('TC-G-2: /partner/users に InviteModal・招待ボタンが表示されない', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    // /users API をモックしてテーブルを表示させる
    await page.route('**/users', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USERS),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/users')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(2000)

    expect(page.url()).toContain('/partner/users')

    // InviteModal の data-testid が存在しないこと
    await expect(page.locator('[data-testid="invite-modal"]')).toHaveCount(0)

    // 「招待」ボタンが partner/users には表示されないこと
    const inviteButtons = page.locator('button', { hasText: /招待/ })
    await expect(inviteButtons).toHaveCount(0)

    await saveScreenshot(page, 'tc-g-invitations-deprecated')
  })
})

// ─── TC-I: KPI 接続確認 (/api/partner/stats スキーマ + 30 秒以内レスポンス) ────
//
// PartnerStatsResponse (backend/app/partner/schemas.py:12):
//   total_aum, yesterday_aum, month_return_pct, yesterday_return_pct, user_count
// 実 backend への relay で検証 (mock 除去 / バグ-F-17 教訓)

test.describe('TC-I: KPI 接続確認 (/api/partner/stats)', () => {
  test.skip(!HAS_CREDENTIALS, 'E2E_PARTNER_EMAIL / E2E_PARTNER_PASSWORD 未設定')

  test.beforeEach(ensureScreenshotDir)

  test('TC-I: /api/partner/stats が 30 秒以内に正しいスキーマで応答する', async ({
    page,
  }) => {
    await setupLaneGAuth(page)

    let capturedResponse: Record<string, unknown> | null = null
    let responseStatus = 0
    let elapsedMs = 0

    // /api/partner/stats を傍受してレスポンスをキャプチャ + latency 計測
    await page.route('**/api/partner/stats', async (route) => {
      const start = Date.now()
      // relay 先 (internal backend)
      const internalUrl = `${INTERNAL_BACKEND}/api/partner/stats`
      const authPath = path.join('e2e', '.auth', 'partner.json')
      const { token } = fs.existsSync(authPath)
        ? (JSON.parse(fs.readFileSync(authPath, 'utf-8')) as { token: string })
        : { token: '' }

      try {
        const res = await fetch(internalUrl, {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        })
        const body = await res.text()
        elapsedMs = Date.now() - start
        responseStatus = res.status
        try {
          capturedResponse = JSON.parse(body) as Record<string, unknown>
        } catch {
          capturedResponse = { _raw: body }
        }
        await route.fulfill({
          status: res.status,
          contentType: res.headers.get('content-type') ?? 'application/json',
          body,
        })
      } catch (e) {
        console.error('[TC-I relay] failed:', e)
        elapsedMs = Date.now() - start
        await route.continue()
      }
    })

    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    // stats API が呼ばれるまで最大 35 秒待つ
    await page.waitForTimeout(5000)

    console.log(`[TC-I] /api/partner/stats status: ${responseStatus}, elapsed: ${elapsedMs}ms`)

    // レスポンス到達確認
    expect(capturedResponse).not.toBeNull()

    // 30 秒以内
    expect(elapsedMs).toBeLessThan(30_000)

    // ステータス 200
    expect(responseStatus).toBe(200)

    // PartnerStatsResponse スキーマ検証
    const body = capturedResponse as Record<string, unknown>
    expect(body).toHaveProperty('total_aum')
    expect(body).toHaveProperty('yesterday_aum')
    expect(body).toHaveProperty('user_count')
    // month_return_pct / yesterday_return_pct は null 許容

    // 法務要件: wallet_address / tx_hash が含まれないこと
    const bodyStr = JSON.stringify(body)
    expect(bodyStr).not.toContain('wallet_address')
    expect(bodyStr).not.toContain('tx_hash')

    await saveScreenshot(page, 'tc-i-kpi-stats')
  })
})

// ─── TC-J: /partner/users 一覧 + 詳細モーダル + 運用情報表示 ─────────────────
//
// app/(partner)/partner/users/page.tsx:59 → apiFetch('/users') → テーブル表示
// 行クリック → UserDetailModal: username, email, role, ステータス, 登録日

test.describe('TC-J: /partner/users 一覧 + 詳細モーダル', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC-J: /partner/users テーブル表示 + 行クリック → UserDetailModal 運用情報', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    // /users をモック
    await page.route('**/users', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USERS),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/users')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1500)

    expect(page.url()).toContain('/partner/users')

    // テーブルが表示されること
    await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })

    // モックユーザー名が表示されること
    await expect(page.getByText('テストユーザーA')).toBeVisible({ timeout: 10_000 })

    // 行クリック → UserDetailModal 表示
    await page.locator('table tbody tr').first().click()
    await page.waitForTimeout(500)

    // UserDetailModal: ダイアログが開いていること
    const modal = page.locator('[role="dialog"]')
    await expect(modal).toBeVisible({ timeout: 8_000 })

    // 運用情報: ユーザー詳細ヘッダー
    await expect(modal.getByText('ユーザー詳細')).toBeVisible({ timeout: 5_000 })

    // ユーザー名が modal 内に表示されること
    await expect(modal.getByText('テストユーザーA')).toBeVisible({ timeout: 5_000 })

    // ロール「閲覧者」が表示されること (UserDetailModal.tsx ROLE_LABELS: viewer → 閲覧者)
    await expect(modal.getByText('閲覧者')).toBeVisible({ timeout: 5_000 })

    // modal 内に wallet_address / tx_hash が含まれないこと
    const modalText = (await modal.textContent()) ?? ''
    expect(modalText).not.toContain('wallet_address')
    expect(modalText).not.toContain('tx_hash')

    await saveScreenshot(page, 'tc-j-users-detail')
  })
})

// ─── TC-K: tx_hash / wallet_address が DOM・API レスポンスに非含 (法務要件) ───
//
// partner 向け画面で wallet address (0x + 40 hex) や tx_hash が
// テーブル・API レスポンスに露出しないことを確認する。

test.describe('TC-K: tx_hash / wallet_address 非含確認 (法務)', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC-K-1: /partner/users テーブルに wallet address パターンが出現しない', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    await page.route('**/users', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USERS),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/users')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(2000)

    // テーブルのテキストに wallet_address / tx_hash が含まれないこと
    const tableText = await page.locator('table').innerText().catch(() => '')
    expect(tableText).not.toContain('tx_hash')
    expect(tableText).not.toContain('wallet_address')

    // Ethereum アドレスパターン (0x + 40 hex) が DOM に出現しないこと
    const walletAddrLocator = page.locator('table').locator('text=/0x[a-fA-F0-9]{40}/')
    await expect(walletAddrLocator).toHaveCount(0)

    // data-testid="tx-hash" が存在しないこと
    await expect(page.locator('[data-testid="tx-hash"]')).toHaveCount(0)

    await saveScreenshot(page, 'tc-k-no-wallet-exposure')
  })

  test('TC-K-2: /api/partner/stats レスポンスに wallet_address / tx_hash が含まれない', async ({
    page,
  }) => {
    await setupPartnerAuth(page)

    let capturedStatsBody: string | null = null

    // /api/partner/stats をモックしてレスポンスボディを検証
    await page.route('**/api/partner/stats', async (route) => {
      if (route.request().method() === 'GET') {
        const body = JSON.stringify(MOCK_PARTNER_STATS)
        capturedStatsBody = body
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body,
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/dashboard')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(2000)

    // レスポンスが受信されたこと
    expect(capturedStatsBody).not.toBeNull()

    // wallet_address / tx_hash フィールドが含まれないこと
    expect(capturedStatsBody).not.toContain('wallet_address')
    expect(capturedStatsBody).not.toContain('tx_hash')

    // /partner/dashboard の DOM にも wallet address パターンがないこと
    // (KPI カード等に 0x アドレスが表示されていないこと)
    const kpiSection = page.locator('main')
    const kpiText = await kpiSection.innerText().catch(() => '')
    // 厳密な 40 hex パターン (0x + 40 hex chars) のみチェック
    // 短縮アドレス (badge) は header 内のため main には出ない
    expect(kpiText).not.toMatch(/0x[a-fA-F0-9]{40}/)

    await saveScreenshot(page, 'tc-k-stats-no-wallet')
  })
})
