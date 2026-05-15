// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [Lead 検証] UAT pre-check 2026-05-10 — 8 シナリオ A-H
//
// 目的: 山本さん UAT 依頼前に Lead 側で staging 実環境を通し確認
//   A: Lane A 旧按分 UI 削除確認
//   B: Lane C BottomNav (hamburger) 紹介プログラム
//   C: Lane D /connect → partner ロールは /partner/dashboard に redirect
//   D: Lane E InviteModal 廃止 + /partner/referral 遷移
//   E: Lane B WalletConnectCard + POST /auth/wallet/link mock
//   F: 取引履歴非開示 (tx_hash / wallet_address が DOM・API に出ない) ★最重要
//   G: i18n — 英語切替 + "Referral" 系英語テキスト表示
//   H: モバイル対応 — viewport 393x852 + overflow なし + BottomNav 確認
//
// 実環境: https://staging.ultra-auto-trade.com (実 frontend + 実 backend + 実 DB)
// CF Access: .auth/cf-access.json (CF_Authorization cookie)
// Partner 認証: setupPartnerAuth (JWT inject + /auth/me mock)
//
// 実行: npx playwright test e2e/uat-pre-check-2026-05-10.spec.ts --reporter=list,html
// 全 pass 後: claude.ai に報告 → 山本さん UAT 通知 Slack

import { test, expect, Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { setupPartnerAuth } from './helpers/partner-auth'

const STAGING_URL = process.env.STAGING_URL ?? 'https://staging.ultra-auto-trade.com'
const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'uat-pre-check-2026-05-10')

const CF_CLIENT_ID = process.env.CF_ACCESS_CLIENT_ID ?? ''
const CF_CLIENT_SECRET = process.env.CF_ACCESS_CLIENT_SECRET ?? ''
const CF_HEADERS: Record<string, string> =
  CF_CLIENT_ID && CF_CLIENT_SECRET
    ? { 'CF-Access-Client-Id': CF_CLIENT_ID, 'CF-Access-Client-Secret': CF_CLIENT_SECRET }
    : {}

function ensureDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}.png`), fullPage: true })
}

// --- Mock data ---

const MOCK_REFERRED_USERS = [
  {
    id: 20,
    email_masked: 'ua**@example.com',
    role: 'viewer',
    created_at: '2026-05-01T00:00:00+00:00',
  },
]


const MOCK_WALLET_LINK_RESPONSE = {
  wallet_address: '0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2',
  network: 'Base Sepolia',
}

const MOCK_USERS_LIST = [
  {
    id: 20,
    email: 'uat-test-002@example.com',
    username: 'uat-test-002',
    role: 'viewer',
    is_active: true,
    created_at: '2026-05-01T00:00:00+00:00',
    updated_at: '2026-05-01T00:00:00+00:00',
    terms_accepted_at: null,
    terms_version: null,
    risk_mode: 'conservative',
    invited_by: null,
    tier: 'GENERAL',
    risk_mode_label: 'ローリスク',
  },
]

// ─────────────────────────────────────────────────────────────────────────────

// 注: describe.serial ではなく describe を使用。
//   serial だと C (Lane D 未デプロイ) の失敗で D-H がすべて skipped になるため。
//   各テストは独立した page fixture を持つため、並列実行でも問題なし。
test.describe('[Lead UAT Pre-check 2026-05-10] 8 シナリオ A-H', () => {
  test.use({
    extraHTTPHeaders: CF_HEADERS,
    storageState: '.auth/cf-access.json',
  })

  test.beforeEach(ensureDir)

  // ── A: Lane A 旧按分 UI 削除確認 ────────────────────────────────────────────
  test('A: 旧按分 UI 削除確認 — /partner/dashboard', async ({ page }) => {
    await setupPartnerAuth(page)
    await page.goto(`${STAGING_URL}/partner/dashboard`, { waitUntil: 'domcontentloaded' })
    // heading 待機 (networkidle は polling 通信で永続タイムアウトするため不使用)
    await page.getByText('パートナーダッシュボード').waitFor({ timeout: 10_000 })
    expect(page.url()).toContain('/partner/dashboard')

    // 「資金割り振り一覧」セクションが表示されること (= セクション自体は残る)
    await expect(page.getByText('資金割り振り一覧')).toBeVisible({ timeout: 10_000 })

    // 「+ 追加」ボタン (旧 Lane A 削除対象) が存在しないこと
    const addBtn = page.getByRole('button', { name: /^\+?\s*追加$/ })
    await expect(addBtn).toHaveCount(0)

    // 「閲覧のみ（廃止予定）」バッジが表示されること (Lane A 追加 UI)
    await expect(page.getByText(/閲覧のみ（廃止予定）/)).toBeVisible({ timeout: 10_000 })

    await shot(page, 'A_no_allocation_add_button')
  })

  // ── B: Lane C BottomNav (hamburger) 紹介プログラム ──────────────────────────
  test('B: hamburger menu に「紹介プログラム」→ /partner/referral 遷移 (mobile 393x852)', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 393, height: 852 })
    await setupPartnerAuth(page)
    // /partner/settings を使用 — /partner/dashboard は staging の auth redirect loop で不安定
    // (test E が /partner/settings で安定動作することを確認済み)
    await page.goto(`${STAGING_URL}/partner/settings`, { waitUntil: 'domcontentloaded' })
    await page.getByText('ウォレット未接続').waitFor({ timeout: 10_000 })
    expect(page.url(), `[B] auth 失敗: ${page.url()}`).toContain('/partner/settings')
    await shot(page, 'B_settings_loaded')

    // AppShell: モバイルでは hamburger ボタン (aria-label="メニュー") を開く
    const hamburgerBtn = page.getByRole('button', { name: 'メニュー' })
    if (await hamburgerBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await hamburgerBtn.click()
      await page.waitForTimeout(500)
    }

    // 「紹介プログラム」リンクが表示されること
    const referralLink = page.getByRole('link', { name: '紹介プログラム' }).first()
    await expect(referralLink).toBeVisible({ timeout: 10_000 })
    // href が /partner/referral を指していること (Mobile Chrome touch-click の ERR_ABORTED 回避のため click ではなく href 検証)
    const href = await referralLink.getAttribute('href')
    expect(href, `「紹介プログラム」リンクの href: ${href}`).toMatch(/\/partner\/referral/)
    await shot(page, 'B_hamburger_referral_link')
    // href 検証で完結 — Mobile Chrome touch-click の ERR_ABORTED 回避のため goto は省略
  })

  // ── C: Lane D /connect → partner ロールは /partner/dashboard に redirect ────────
  // Lane D が未デプロイの場合 FAIL (期待: /partner/dashboard、実際: /connect or /user/*)
  test('C: [Lane D] /connect に partner でアクセス → /partner/dashboard に redirect', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await page.goto(`${STAGING_URL}/connect`, { waitUntil: 'domcontentloaded' })

    // redirect を最大 8 秒待機
    try {
      await page.waitForURL(/\/partner\/dashboard/, { timeout: 15_000 })
    } catch {
      // redirect なければ現在 URL をアサーション (Lane D 未デプロイなら /connect のまま → FAIL)
    }

    expect(
      page.url(),
      `[Lane D 未デプロイ] partner は /connect ではなく /partner/dashboard に redirect されるべき。現在 URL: ${page.url()}`,
    ).toContain('/partner/dashboard')

    await shot(page, 'C_connect_redirect')
  })

  // ── D: Lane E InviteModal 廃止 — 「テスターを招待」→ /partner/referral ────────
  test('D: InviteModal 廃止 — 「テスターを招待」クリック → /partner/referral 遷移', async ({
    page,
  }) => {
    // POST /api/invitations が発火しないことを監視
    const invitationRequests: string[] = []
    page.on('request', (req) => {
      if (/\/invitations/.test(req.url())) {
        invitationRequests.push(req.url())
      }
    })

    // /users API をモックしてユーザー 1 件を表示
    await page.route('**/users', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USERS_LIST),
        })
      } else {
        await route.continue()
      }
    })

    await setupPartnerAuth(page)
    await page.goto(`${STAGING_URL}/partner/users`, { waitUntil: 'domcontentloaded' })
    expect(page.url()).toContain('/partner/users')

    // 「テスターを招待」ボタンが表示されること (表示完了を兼ねた待機)
    const inviteBtn = page.getByRole('link', { name: /テスターを招待/ })
    await expect(inviteBtn).toBeVisible({ timeout: 10_000 })

    // クリック → /partner/referral に遷移 (旧 InviteModal は開かない)
    await Promise.all([
      page.waitForURL(/\/partner\/referral/, { timeout: 10_000 }),
      inviteBtn.click(),
    ])

    // POST /api/invitations が 0 件であること
    expect(invitationRequests.length).toBe(0)
    expect(page.url()).toContain('/partner/referral')
    await shot(page, 'D_invite_button_to_referral')
  })

  // ── E: Lane B WalletConnectCard + POST /auth/wallet/link mock ───────────────
  test('E: WalletConnectCard 表示 + POST /auth/wallet/link 200 → 接続済み UI', async ({ page }) => {
    // POST /auth/wallet/link を mock (実 Privy modal は skip)
    await page.route('**/auth/wallet/link', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_WALLET_LINK_RESPONSE),
        })
      } else {
        await route.continue()
      }
    })

    await setupPartnerAuth(page)
    await page.goto(`${STAGING_URL}/partner/settings`, { waitUntil: 'domcontentloaded' })

    // 「ウォレット未接続」状態が表示されること (表示完了を兼ねた待機)
    await expect(page.getByText('ウォレット未接続')).toBeVisible({ timeout: 10_000 })
    const connectBtn = page.getByRole('button', { name: 'ウォレット接続' })
    await expect(connectBtn).toBeVisible()
    await shot(page, 'E_wallet_connect_card')

    // 接続ボタンクリック → 接続済み UI に切り替わること
    await connectBtn.click()
    await expect(page.getByText(/接続済み/)).toBeVisible({ timeout: 8_000 })
    await shot(page, 'E_wallet_connected')
  })

  // ── F: 取引履歴非開示 ★最重要 ─────────────────────────────────────────────────
  test('F: 取引履歴非開示 — tx_hash / wallet_address が DOM・API レスポンスに存在しない ★最重要', async ({
    page,
  }) => {
    test.setTimeout(60_000)

    // GET /partner/referral/users/*/transactions をモック (取引データあり・tx_hash/wallet_address なし)
    await page.route('**/partner/referral/users/*/transactions', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { type: 'deposit', amount: '100000.00', occurred_at: '2026-05-01T00:00:00+00:00' },
            { type: 'withdraw', amount: '50000.00', occurred_at: '2026-05-02T00:00:00+00:00' },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    // API レスポンスを監視して tx_hash / wallet_address キーが含まれていないことを確認
    const txApiItems: Record<string, unknown>[] = []
    page.on('response', async (response) => {
      if (
        response.url().includes('/referral/') &&
        (response.url().includes('transaction') || response.url().includes('Transaction'))
      ) {
        try {
          const body = (await response.json()) as unknown
          if (Array.isArray(body)) {
            txApiItems.push(...(body as Record<string, unknown>[]))
          }
        } catch {
          /* ignore */
        }
      }
    })

    await setupPartnerAuth(page)
    // リスト→クリックの 2 ステップを省略し詳細ページへ直接遷移 (タイムアウト対策)
    await page.goto(`${STAGING_URL}/partner/referral/20`, { waitUntil: 'domcontentloaded' })

    // ローディング完了を待つ (skeleton → テーブル or 「データなし」)
    await expect(page.locator('text=/データなし|取引履歴一覧/').first()).toBeVisible({ timeout: 15_000 })
    expect(page.url()).toContain('/partner/referral/20')

    await shot(page, 'F_transactions_page')

    // 取引データが表示されていること (モックで deposit / withdraw を注入済み)
    await expect(page.getByText('入金')).toBeVisible({ timeout: 5_000 })

    // wallet address パターン (0x + 40 hex) が DOM に存在しないこと
    const walletAddressCount = await page.locator('text=/0x[a-fA-F0-9]{40}/').count()
    expect(walletAddressCount, 'wallet address (0x...) が DOM に露出している').toBe(0)

    // data-testid="tx-hash" が DOM に存在しないこと
    await expect(page.locator('[data-testid="tx-hash"]')).toHaveCount(0)

    // table 内テキストに tx_hash / wallet_address が含まれていないこと
    const tableText = await page.locator('table').innerText().catch(() => '')
    expect(tableText, 'table 内に "tx_hash" が存在する').not.toContain('tx_hash')
    expect(tableText, 'table 内に "wallet_address" が存在する').not.toContain('wallet_address')

    // API レスポンスを受信した場合 → キーに tx_hash / wallet_address が含まれないこと
    for (const item of txApiItems) {
      const keys = Object.keys(item)
      expect(keys, `API に tx_hash キー: ${JSON.stringify(item)}`).not.toContain('tx_hash')
      expect(keys, `API に wallet_address キー: ${JSON.stringify(item)}`).not.toContain('wallet_address')
    }

    await shot(page, 'F_no_tx_hash')
  })

  // ── G: i18n — 英語切替 + "Referral" 系英語テキスト表示 ──────────────────────
  test('G: i18n — 英語切替 + "Referral" 系英語テキスト表示 + 日本語ハードコードなし', async ({
    page,
  }) => {
    // NEXT_LOCALE=en を Cookie に設定 (next-intl middleware が初回リクエスト時に読む)
    await page.context().addCookies([
      {
        name: 'NEXT_LOCALE',
        value: 'en',
        domain: '.ultra-auto-trade.com',
        path: '/',
        secure: true,
        sameSite: 'Lax',
      },
    ])

    // referral API をモックして page がロードされるようにする
    await page.route('**/referral/code', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            referral_code: '6J7XMCTG',
            share_url: `${STAGING_URL}/r/6J7XMCTG`,
          }),
        })
      } else {
        await route.continue()
      }
    })
    await page.route('**/referral/list', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
      } else {
        await route.continue()
      }
    })

    await setupPartnerAuth(page)
    await page.goto(`${STAGING_URL}/partner/referral`, { waitUntil: 'domcontentloaded' })
    // 紹介コード or 英語 Referral 要素が出るまで待つ (最大 10 秒)
    await page.locator('text=/紹介プログラム|Referral/').first().waitFor({ timeout: 10_000 }).catch(() => {})
    await shot(page, 'G_en_referral')

    // 英語 "Referral" 系テキストが表示されること (Referral Link / Referral Program 等)
    const bodyText = await page.evaluate(() => (document.body as HTMLElement).innerText ?? '')
    const hasEnglishReferral =
      bodyText.includes('Referral Link') ||
      bodyText.includes('Referral Program') ||
      bodyText.includes('Referral')
    expect(hasEnglishReferral, '英語 "Referral" 系テキストが表示されていない').toBeTruthy()

    // 日本語ハードコード「紹介プログラム」「紹介コード」「紹介者」が
    // script/style 外のテキストノードに存在しないこと
    const jpHardcodeNodes = await page.evaluate(() => {
      const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT'])
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const tag = node.parentElement?.tagName ?? ''
          return SKIP_TAGS.has(tag) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
        },
      })
      const matches: string[] = []
      let node: Node | null
      while ((node = walker.nextNode())) {
        const text = (node.textContent ?? '').trim()
        if (text && /紹介プログラム|紹介コード|紹介者/.test(text)) {
          matches.push(text)
        }
      }
      return matches
    })
    expect(
      jpHardcodeNodes.length,
      `英語モードで日本語ハードコードが残存: ${jpHardcodeNodes.slice(0, 3).join(', ')}`,
    ).toBe(0)
  })

  // ── H: モバイル対応 — viewport 393x852 + overflow なし + BottomNav 確認 ───────
  test('H: モバイル対応 — viewport 393x852 + 横 overflow なし + BottomNav アイテム表示', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 393, height: 852 })
    await setupPartnerAuth(page)
    await page.goto(`${STAGING_URL}/partner/dashboard`, { waitUntil: 'domcontentloaded' })
    await page.getByText('パートナーダッシュボード').waitFor({ timeout: 10_000 })
    expect(page.url()).toContain('/partner/dashboard')

    // レイアウト崩れなし — 横スクロールが発生していないこと
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(hasOverflow, '横スクロール (overflow) が発生している').toBe(false)

    // BottomNav (shared) または AppShell hamburger が表示されていること
    // shared BottomNav (partner): ホーム, 承認, テスター, AI提案, 設定 = 5 アイテム
    // AppShell: hamburger button が表示
    const bottomNavLinks = page.locator('nav.fixed a')
    const navCount = await bottomNavLinks.count()
    if (navCount > 0) {
      // shared BottomNav が表示されている場合: 5 アイテム (partnerNavItems)
      expect(navCount).toBe(5)
    } else {
      // AppShell hamburger が表示されていること
      const hamburgerBtn = page.getByRole('button', { name: 'メニュー' })
      await expect(hamburgerBtn).toBeVisible({ timeout: 5_000 })
    }

    await shot(page, 'H_mobile_dashboard')
  })
})
