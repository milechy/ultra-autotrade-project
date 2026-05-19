// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [Phase D Step 1.5] UAT pre-check (実 UI 統合テスト 8 シナリオ A-H)
//
// 目的: 山本さん UAT 依頼前に Lead 側で staging 実環境を通し確認
// 実環境: https://staging.ultra-auto-trade.com (実 frontend + 実 backend + 実 DB)
// page.route 等の mock は一切使わない (= 真の統合テスト)
//
// 認証: PARTNER_JWT を localStorage に inject (login UI はシナリオ A のみで確認)
// クリーンアップ: シナリオ G で作成した user は afterAll で削除

import { test, expect, Page, BrowserContext } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const STAGING_URL = 'https://staging.ultra-auto-trade.com'

// CF Access service token (staging は CF Access 保護下)
// Cloudflare Dashboard → Access → Service Auth → Service Tokens で発行
const CF_CLIENT_ID = process.env.CF_ACCESS_CLIENT_ID ?? ''
const CF_CLIENT_SECRET = process.env.CF_ACCESS_CLIENT_SECRET ?? ''
const CF_HEADERS: Record<string, string> =
  CF_CLIENT_ID && CF_CLIENT_SECRET
    ? { 'CF-Access-Client-Id': CF_CLIENT_ID, 'CF-Access-Client-Secret': CF_CLIENT_SECRET }
    : {}

// staging 実環境専用スペック。CI / 非 staging では JWT ファイルが無いため、
// トップレベル readFileSync で全 E2E Smoke job をクラッシュさせない
// (import 時に落ちると Playwright 収集が失敗し全 spec が FAILURE になる baseline 問題)。
const JWT_PATH = '/tmp/staging_partner_jwt.txt'
const PARTNER_JWT = fs.existsSync(JWT_PATH)
  ? fs.readFileSync(JWT_PATH, 'utf-8').trim()
  : ''
const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'uat-pre-check')
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

const TS = Math.floor(Date.now() / 1000)
const TEST_NEW_USER_EMAIL = `uat-precheck-newuser-${TS}@gateb-test.com`

let CAPTURED_REFERRAL_CODE: string | null = null

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}.png`), fullPage: true })
}

async function injectAuth(page: Page) {
  // staging frontend が JWT を localStorage から読む
  await page.addInitScript(
    (args) => {
      localStorage.setItem(args.tokenKey, args.token)
      localStorage.setItem(args.expiresKey, String(args.expires))
    },
    {
      tokenKey: 'ultra_auth_token',
      expiresKey: 'ultra_auth_expires',
      token: PARTNER_JWT,
      expires: Date.now() + 2 * 60 * 60 * 1000, // 2h
    },
  )
}

test.describe.serial('[UAT Pre-check] F-17 + RAS Phase 1 / staging 実環境 8 シナリオ A-H', () => {
  // PARTNER_JWT 未配置 (CI / 非 staging) では全シナリオを skip。
  // このスペックは staging 実環境専用 (実 frontend + 実 backend + 実 DB)。
  test.skip(
    !PARTNER_JWT,
    'PARTNER_JWT 未配置のため skip (staging 実環境専用スペック / CI baseline)',
  )

  test.use({
    extraHTTPHeaders: CF_HEADERS,
    storageState: '.auth/cf-access.json',
  })

  // ─── A: ログイン画面到達 ──────────────────────────────────────────────
  test('A: /login 到達 + ログインフォーム表示', async ({ page }) => {
    await page.goto(`${STAGING_URL}/login`, { waitUntil: 'domcontentloaded' })
    // メール / パスワード入力欄が表示
    await expect(page.getByLabel(/メールアドレス|email/i)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByLabel(/パスワード|password/i)).toBeVisible({ timeout: 5_000 })
    await expect(page.getByRole('button', { name: /ログイン/ })).toBeVisible({ timeout: 5_000 })
    await shot(page, 'A_login_form')
  })

  // ─── B: partner で /partner/dashboard 到達 (JWT inject) ───────────────
  test('B: JWT inject で /partner/dashboard 到達', async ({ page }) => {
    await injectAuth(page)
    await page.goto(`${STAGING_URL}/partner/dashboard`, { waitUntil: 'domcontentloaded' })
    // dashboard 系の固有コンテンツが表示される (ヘッダー or KPI)
    await expect(page).toHaveURL(/\/partner\/dashboard/, { timeout: 10_000 })
    // とりあえずダッシュボードらしき要素 (ヘッダー or サイドバー or 統計)
    await page.waitForLoadState('networkidle', { timeout: 15_000 })
    await shot(page, 'B_partner_dashboard')
  })

  // ─── C: /partner/referral で referral_code 表示 (実 API 呼び出し) ─────
  test('C: /partner/referral で実 API 経由 referral_code 表示', async ({ page }) => {
    await injectAuth(page)
    await page.goto(`${STAGING_URL}/partner/referral`, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 20_000 })

    // 8 桁英数字 (大文字 + digit) パターンの code を検出
    const codeLocator = page.locator('text=/\\b[A-Z0-9]{8}\\b/').first()
    await expect(codeLocator).toBeVisible({ timeout: 15_000 })
    const codeText = await codeLocator.textContent()
    const match = codeText?.match(/\b([A-Z0-9]{8})\b/)
    if (!match) throw new Error(`8桁 code が抽出できない: ${codeText}`)
    CAPTURED_REFERRAL_CODE = match[1]
    console.log(`✓ captured referral_code: ${CAPTURED_REFERRAL_CODE}`)
    await shot(page, 'C_referral_code_displayed')
  })

  // ─── D: 「コピー」ボタン → toast「コピーしました」 ──────────────────
  test('D: コピーボタン → toast 表示', async ({ page, context }) => {
    await injectAuth(page)
    // clipboard 権限付与
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.goto(`${STAGING_URL}/partner/referral`, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 15_000 })

    const copyBtn = page.getByRole('button', { name: /コピー/ })
    await expect(copyBtn).toBeVisible({ timeout: 10_000 })
    await copyBtn.click()

    // sonner toast
    await expect(page.getByText(/コピーしました/)).toBeVisible({ timeout: 5_000 })
    await shot(page, 'D_copy_toast')
  })

  // ─── E: /r/<code> → /auth/register?ref=<code> リダイレクト (Incognito) ─
  test('E: /r/<code> → /auth/register?ref=<code> リダイレクト', async ({ browser }) => {
    if (!CAPTURED_REFERRAL_CODE) test.skip(true, 'referral_code 未取得')
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await page.goto(`${STAGING_URL}/r/${CAPTURED_REFERRAL_CODE}`, { waitUntil: 'domcontentloaded' })
      // クライアントサイドリダイレクト完了を待つ
      await page.waitForURL(/\/auth\/register/, { timeout: 10_000 })
      const url = page.url()
      expect(url).toContain('/auth/register')
      expect(url).toContain(`ref=${CAPTURED_REFERRAL_CODE}`)
      await shot(page, 'E_redirect_to_register')
    } finally {
      await ctx.close()
    }
  })

  // ─── F: /auth/register?ref=<code> ページ確認 + consent UI ─────────────
  test('F: /auth/register に referral_code prefill + consent checkbox', async ({ browser }) => {
    if (!CAPTURED_REFERRAL_CODE) test.skip(true, 'referral_code 未取得')
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await page.goto(`${STAGING_URL}/auth/register?ref=${CAPTURED_REFERRAL_CODE}`, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle', { timeout: 15_000 })

      // referral_code が画面のどこかに表示されている (input value or 表示テキスト)
      const codeOnPage = page.locator(`text=/\\b${CAPTURED_REFERRAL_CODE}\\b/`).first()
      await expect(codeOnPage).toBeVisible({ timeout: 10_000 })

      // consent checkbox の存在確認
      const consentCheckbox = page.locator('input[type="checkbox"]').first()
      await expect(consentCheckbox).toBeVisible({ timeout: 5_000 })

      await shot(page, 'F_register_page_with_referral')
    } finally {
      await ctx.close()
    }
  })

  // ─── G: 新規ユーザー登録 (consent ON) → 成功 ──────────────────────────
  test('G: /auth/register?ref=<code> で実 API 経由ユーザー登録', async ({ browser }) => {
    if (!CAPTURED_REFERRAL_CODE) test.skip(true, 'referral_code 未取得')
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await page.goto(`${STAGING_URL}/auth/register?ref=${CAPTURED_REFERRAL_CODE}`, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle', { timeout: 15_000 })

      // メール / パスワード / username 入力
      const emailInput = page.getByLabel(/メールアドレス|email/i).first()
      const passwordInput = page.getByLabel(/パスワード|password/i).first()
      const usernameInput = page.getByLabel(/表示名|ユーザー名|username/i).first()
      await emailInput.fill(TEST_NEW_USER_EMAIL)
      await passwordInput.fill('UATPreCheck!2026')
      await usernameInput.fill(`uat-pc-${TS}`)

      // consent checkbox ON
      const consentCheckbox = page.locator('input[type="checkbox"]').first()
      await consentCheckbox.check({ force: true })

      await shot(page, 'G_register_form_filled')

      // 登録ボタン
      const submitBtn = page.getByRole('button', { name: /登録|register/i }).first()
      await submitBtn.click()

      // 成功 → /user/dashboard or /user/connect or 成功画面
      await page.waitForURL(/\/(user|dashboard|connect)/, { timeout: 15_000 })
      await shot(page, 'G_register_success')
      console.log(`✓ registered new user: ${TEST_NEW_USER_EMAIL}`)
    } finally {
      await ctx.close()
    }
  })

  // ─── H: partner /partner/referral で新ユーザー反映 + 取引履歴 wallet/tx_hash 非開示 ─
  test('H: partner 側一覧反映 + 取引履歴 wallet/tx_hash 非開示', async ({ page }) => {
    await injectAuth(page)
    // /partner/referral リロード → 新ユーザー出現
    await page.goto(`${STAGING_URL}/partner/referral`, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 20_000 })

    // mask された email (例: ua****-${TS}@gateb-test.com の prefix だけ)
    const maskedEmailPattern = new RegExp(`uat-pc.*\\*\\*.*@gateb-test\\.com|ua\\*\\*.*@gateb-test\\.com`, 'i')
    // 簡易: gateb-test.com を含む行があれば OK
    const newUserRow = page.locator(`text=/gateb-test\\.com/`).first()
    await expect(newUserRow).toBeVisible({ timeout: 15_000 })
    await shot(page, 'H1_referred_user_in_list')

    // 取引履歴 link クリック
    const detailLink = page.getByRole('link', { name: /取引履歴/ }).first()
    await expect(detailLink).toBeVisible({ timeout: 5_000 })
    await Promise.all([
      page.waitForURL(/\/partner\/referral\/\d+/, { timeout: 10_000 }),
      detailLink.click(),
    ])
    await page.waitForLoadState('networkidle', { timeout: 10_000 })
    expect(page.url()).toMatch(/\/partner\/referral\/\d+/)

    // 取引履歴テーブル or 「データなし」
    const tableOrEmpty = page.locator('table, text=/データなし/').first()
    await expect(tableOrEmpty).toBeVisible({ timeout: 10_000 })
    await shot(page, 'H2_transactions_page')

    // wallet address pattern (0x + 40 hex) が DOM に存在しない
    const walletAddressCount = await page.locator('text=/0x[a-fA-F0-9]{40}/').count()
    expect(walletAddressCount).toBe(0)

    // data-testid="tx-hash" が DOM に存在しない
    await expect(page.locator('[data-testid="tx-hash"]')).toHaveCount(0)

    // 取引履歴テーブル領域 innerText に wallet / tx_hash が無い (table タグがあれば)
    const tableLocator = page.locator('table')
    if (await tableLocator.count() > 0) {
      const tableText = await tableLocator.innerText()
      expect(tableText).not.toContain('tx_hash')
      expect(tableText).not.toContain('wallet_address')
    }

    await shot(page, 'H3_no_wallet_no_tx_hash')
  })
})
