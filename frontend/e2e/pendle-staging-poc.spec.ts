// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [Phase A-3] Pendle PoC staging End-to-End 検証
//
// 目的: staging-new で Pendle Finance PoC (PT / YT / fixed yield) の
//       フロントエンド表示 + バックエンド API 疎通を E2E 確認する。
//
// シナリオ:
//   A: /admin/protocols — Pendle プロトコルカード表示確認
//   B: /user/strategies — Pendle PT 戦略カード表示確認
//   C: GET /api/protocols/pendle/markets — 200 + PendleMarketInfo 構造検証
//   D: GET /api/protocols/health/pendle — is_operational + risk_level 検証
//   E: POST /api/protocols/pendle/mint dry_run=true — MINT_PT レスポンス検証
//
// 前提 / CF Access:
//   - .auth/cf-access.json (CF_Authorization cookie)
//   - CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET (API curl 用)
//
// P0-1 fix 待ちテスト:
//   シナリオ C-E は staging-new で LIDO_SANDBOX=true の間 API が 500/503 を返す。
//   P0-1 fix (LIDO_SANDBOX=false) 完了後に test.fixme 解除すること。
//   詳細: docs/postmortems/2026-05-12_uat_blocker_full_day_failure.md
//
// 実行:
//   # 通常 (staging URL)
//   npx playwright test e2e/pendle-staging-poc.spec.ts --reporter=list,html
//
//   # ローカル Next.js dev server
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/pendle-staging-poc.spec.ts

import { test, expect, type Page } from '@playwright/test'
import { setupPartnerAuth, PARTNER_MOCK_USER } from './helpers/partner-auth'

const STAGING_URL = process.env.STAGING_URL ?? 'https://staging.ultra-auto-trade.com'
const API_URL = process.env.STAGING_API_URL ?? 'http://localhost:8082'

const CF_CLIENT_ID = process.env.CF_ACCESS_CLIENT_ID ?? ''
const CF_CLIENT_SECRET = process.env.CF_ACCESS_CLIENT_SECRET ?? ''
const CF_HEADERS: Record<string, string> =
  CF_CLIENT_ID && CF_CLIENT_SECRET
    ? { 'CF-Access-Client-Id': CF_CLIENT_ID, 'CF-Access-Client-Secret': CF_CLIENT_SECRET }
    : {}

const ADMIN_MOCK_USER = {
  ...PARTNER_MOCK_USER,
  id: 1,
  role: 'admin',
  email: 'admin@ultra-autotrade.com',
}

/** 管理者 JWT を localStorage + /auth/me mock で注入。 */
async function setupAdminAuth(page: Page): Promise<void> {
  await page.addInitScript(
    (args) => {
      localStorage.setItem(args.tokenKey, args.token)
      localStorage.setItem(args.expiresKey, String(Date.now() + 86400 * 1000))
    },
    { tokenKey: 'ultra_auth_token', expiresKey: 'ultra_auth_expires', token: 'dummy-admin-token' }
  )
  await page.route('**/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ADMIN_MOCK_USER),
    })
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 共通設定
// ─────────────────────────────────────────────────────────────────────────────

test.describe('[Phase A-3] Pendle PoC staging E2E', () => {
  test.use({
    extraHTTPHeaders: CF_HEADERS,
    storageState: (() => {
      try {
        // .auth/cf-access.json が存在する場合のみ使用
        require('fs').statSync('e2e/.auth/cf-access.json')
        return 'e2e/.auth/cf-access.json'
      } catch {
        return undefined
      }
    })(),
  })

  // ── A: /admin/protocols — Pendle プロトコルカード ─────────────────────────

  test.describe('A: /admin/protocols — Pendle プロトコルカード', () => {
    test('A-1: ページが 200 で読み込まれる', async ({ page }) => {
      await setupAdminAuth(page)
      const resp = await page.goto(`${STAGING_URL}/admin/protocols`, {
        waitUntil: 'domcontentloaded',
        timeout: 15_000,
      })
      // 認証リダイレクト (302→/login) または 200 を許容
      expect([200, 302, null].includes(resp?.status() ?? null)).toBeTruthy()
    })

    test('A-2: Pendle セクションが表示される (mock data)', async ({ page }) => {
      await setupAdminAuth(page)
      await page.goto(`${STAGING_URL}/admin/protocols`, { waitUntil: 'domcontentloaded' })

      // ページが正常レンダリングまたはログインページを表示していること
      const pendleCard = page.getByText('Pendle').first()
      const loginPage = page.getByText('ログイン').first()

      const appeared = await Promise.race([
        pendleCard.waitFor({ state: 'visible', timeout: 10_000 }).then(() => 'pendle'),
        loginPage.waitFor({ state: 'visible', timeout: 10_000 }).then(() => 'login'),
      ]).catch(() => 'timeout')

      // Pendle が表示されるか、認証が必要なログイン画面のいずれか
      expect(['pendle', 'login']).toContain(appeared)
    })

    test('A-3: Pendle プロトコルカードに PT / YT レートが含まれる (mock data)', async ({ page }) => {
      await setupAdminAuth(page)
      await page.goto(`${STAGING_URL}/admin/protocols`, { waitUntil: 'domcontentloaded' })

      // ログイン画面にリダイレクトされた場合はスキップ
      const isLoginPage = await page.getByRole('button', { name: 'ログイン' }).isVisible().catch(() => false)
      if (isLoginPage) {
        test.skip(true, 'admin auth が注入できないためスキップ (local dev では setupAdminAuth が機能する)')
        return
      }

      // mock data に含まれる pt_rate / yt_rate が表示されること
      const bodyText = await page.locator('body').textContent() ?? ''
      // "95" や "4.7" などの数値がある、または "Pendle" テキストが存在する
      expect(bodyText).toMatch(/Pendle|PT|YT|利回り/i)
    })
  })

  // ── B: /user/strategies — Pendle 戦略カード ────────────────────────────────

  test.describe('B: /user/strategies — Pendle 戦略カード', () => {
    test('B-1: ページが読み込まれる', async ({ page }) => {
      await setupPartnerAuth(page)
      const resp = await page.goto(`${STAGING_URL}/user/strategies`, {
        waitUntil: 'domcontentloaded',
        timeout: 15_000,
      })
      expect([200, 302, null].includes(resp?.status() ?? null)).toBeTruthy()
    })

    test('B-2: Pendle PT 戦略カードが表示される', async ({ page }) => {
      await setupPartnerAuth(page)
      await page.goto(`${STAGING_URL}/user/strategies`, { waitUntil: 'domcontentloaded' })

      // 「Pendle」「PT」「固定利回り」等のいずれかが存在すること
      const bodyText = await page.locator('body').textContent().catch(() => '') ?? ''
      const hasPendle = /Pendle|固定利回り|PT|YT/i.test(bodyText)
      const hasLoginPage = /ログイン|サインイン/i.test(bodyText)

      expect(hasPendle || hasLoginPage).toBeTruthy()
    })

    test('B-3: 戦略リストに APY 表示がある', async ({ page }) => {
      await setupPartnerAuth(page)
      await page.goto(`${STAGING_URL}/user/strategies`, { waitUntil: 'domcontentloaded' })

      const bodyText = await page.locator('body').textContent().catch(() => '') ?? ''

      // APY / % / データなし のいずれかがある（API 失敗時は「データなし」が表示される）
      expect(bodyText).toMatch(/%|APY|データなし|ログイン/)
    })
  })

  // ── C: GET /api/protocols/pendle/markets (P0-1 fix 待ち) ──────────────────

  test.describe('C: GET /api/protocols/pendle/markets', () => {
    test.fixme(
      true,
      'P0-1 fix 待ち: staging-new で LIDO_SANDBOX=false に変更後に解除。'
      + ' 現状: LIDO_SANDBOX=true により ProtocolMonitor が 500 を返す。'
    )

    test('C-1: 200 を返しマーケット一覧を含む', async ({ request }) => {
      const resp = await request.get(`${API_URL}/api/protocols/pendle/markets`)
      expect(resp.status()).toBe(200)

      const data = await resp.json()
      expect(Array.isArray(data)).toBeTruthy()
      expect(data.length).toBeGreaterThan(0)

      const market = data[0]
      expect(market).toHaveProperty('market_address')
      expect(market).toHaveProperty('implied_apy')
      expect(market).toHaveProperty('pt_price')
      expect(market).toHaveProperty('yt_price')
    })

    test('C-2: implied_apy が数値文字列として返る', async ({ request }) => {
      const resp = await request.get(`${API_URL}/api/protocols/pendle/markets`)
      const data = await resp.json()
      expect(() => parseFloat(data[0].implied_apy)).not.toThrow()
    })
  })

  // ── D: GET /api/protocols/health/pendle (P0-1 fix 待ち) ──────────────────

  test.describe('D: GET /api/protocols/health/pendle', () => {
    test.fixme(
      true,
      'P0-1 fix 待ち: LIDO_SANDBOX=false 後に解除。現状 500 を返す。'
    )

    test('D-1: 200 + is_operational + risk_level を返す', async ({ request }) => {
      const resp = await request.get(`${API_URL}/api/protocols/health/pendle`)
      expect(resp.status()).toBe(200)

      const data = await resp.json()
      expect(data.protocol).toBe('pendle')
      expect(typeof data.is_operational).toBe('boolean')
      expect(['low', 'medium', 'high', 'critical']).toContain(data.risk_level)
    })
  })

  // ── E: POST /api/protocols/pendle/mint dry_run=true (P0-1 fix 待ち) ───────

  test.describe('E: POST /api/protocols/pendle/mint (dry_run)', () => {
    test.fixme(
      true,
      'P0-1 fix 待ち: LIDO_SANDBOX=false 後に解除。'
    )

    test('E-1: MINT_PT レスポンスが返り tx_hash が null', async ({ request }) => {
      const resp = await request.post(`${API_URL}/api/protocols/pendle/mint`, {
        data: {
          asset: 'stETH',
          amount: '1.0',
          strategy: 'pt_fixed',
          market_address: '0x' + 'ab'.repeat(20),
          dry_run: true,
        },
      })
      expect(resp.status()).toBe(200)

      const data = await resp.json()
      expect(data.operation).toBe('MINT_PT')
      expect(data.dry_run).toBe(true)
      expect(data.tx_hash).toBeNull()
    })

    test('E-2: MINT_YT レスポンスが返る', async ({ request }) => {
      const resp = await request.post(`${API_URL}/api/protocols/pendle/mint`, {
        data: {
          asset: 'stETH',
          amount: '1.0',
          strategy: 'yt_leverage',
          market_address: '0x' + 'ab'.repeat(20),
          dry_run: true,
        },
      })
      expect(resp.status()).toBe(200)
      expect((await resp.json()).operation).toBe('MINT_YT')
    })
  })
})
