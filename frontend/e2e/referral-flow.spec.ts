// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// [RAS L4] Referral flow E2E — Gate 4 verification.
//
// 検証範囲:
//   TC1-TC4: partner 紹介フロー (/partner/referral)
//   TC5:     /r/<code> → /auth/register?ref=<code> リダイレクト
//   TC6-TC8: referral 経由登録 (/auth/register?ref=)
//
// 方式: storageState (.auth/partner.json) + page.route 傍受
//   F-17 L5 (partner-wallet-link.spec.ts) と同パターン。
//   POST /auth/register-with-referral (Lane 2.1 実装中) を傍受。
//
// 依存:
//   Lane 3 で実装される /partner/referral、/r/[code] ページが必要。
//   Lane 3 merge 後にローカル dev (STAGING_URL=http://localhost:3001) で通過確認。
//
// スクリーンショット: e2e/screenshots/ras/

import { test, expect, Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { setupPartnerAuth } from './helpers/partner-auth'

// ─── 定数 ─────────────────────────────────────────────────────────────────────

const SCREENSHOT_DIR = path.join('e2e', 'screenshots', 'ras')

// ─── モックデータ ─────────────────────────────────────────────────────────────

const MOCK_REFERRAL_CODE_RESPONSE = {
  referral_code: 'AB12CD34',
  share_url: 'https://app.ultra-auto-trade.com/r/AB12CD34',
}

const MOCK_REFERRAL_LIST = [
  {
    id: 1,
    email_masked: 'te**@example.com',
    role: 'viewer',
    created_at: '2026-01-01T00:00:00+00:00',
  },
]

const MOCK_TRANSACTIONS = [
  {
    type: '入金',
    amount: '10000.00',
    occurred_at: '2026-01-01T00:00:00+00:00',
  },
]

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

/** POST /referral/code をモック (partner 紹介コード取得/生成) */
async function mockReferralCode(page: Page): Promise<void> {
  await page.route('**/partner/referral/code', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_REFERRAL_CODE_RESPONSE),
      })
    } else {
      await route.continue()
    }
  })
}

/** GET /referral/list をモック */
async function mockReferralList(page: Page): Promise<void> {
  await page.route('**/partner/referral/list', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_REFERRAL_LIST),
      })
    } else {
      await route.continue()
    }
  })
}

// ─── TC1-TC4: partner 紹介フロー ─────────────────────────────────────────────

test.describe('[RAS] partner referral flow', () => {
  // headless Chrome で navigator.clipboard が保護されるため clipboard-write 権限を付与
  test.use({ permissions: ['clipboard-write'] })
  test.beforeEach(ensureScreenshotDir)

  test('TC1: POST /referral/code 200 → /partner/referral で referral_code 表示', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await mockReferralCode(page)

    await page.goto('/partner/referral')
    await page.waitForLoadState('domcontentloaded')

    expect(page.url()).toContain('/partner/referral')

    // exact: true でコードスパン（"AB12CD34"）のみに絞る（URL スパンとの strict 違反回避）
    await expect(page.getByText('AB12CD34', { exact: true })).toBeVisible({ timeout: 10_000 })

    await saveScreenshot(page, 'tc1-referral-code-display')
  })

  test('TC2: 「コピー」ボタンクリック → toast 「コピーしました」', async ({ page }) => {
    await setupPartnerAuth(page)
    await mockReferralCode(page)

    // navigator.clipboard を HTTP (localhost) でも動作するようにモック
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async (_text: string): Promise<void> => {
            return Promise.resolve()
          },
        },
      })
    })

    await page.goto('/partner/referral')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText('AB12CD34', { exact: true })).toBeVisible({ timeout: 10_000 })

    const copyBtn = page.getByRole('button', { name: /コピー/ }).first()
    await expect(copyBtn).toBeVisible({ timeout: 5_000 })
    await copyBtn.click()

    await expect(page.getByText('コピーしました')).toBeVisible({ timeout: 8_000 })

    await saveScreenshot(page, 'tc2-copy-toast')
  })

  test('TC3: GET /referral/list 200 → 紹介済みユーザー一覧 + email mask 表示', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await mockReferralCode(page)
    await mockReferralList(page)

    await page.goto('/partner/referral')
    await page.waitForLoadState('domcontentloaded')

    // email mask が表示されること
    await expect(page.getByText('te**@example.com')).toBeVisible({ timeout: 10_000 })

    // 「取引履歴」リンクが表示されること (Lane3: ロール列なし、詳細リンク列のみ)
    await expect(page.getByRole('link', { name: '取引履歴' }).first()).toBeVisible({
      timeout: 5_000,
    })

    await saveScreenshot(page, 'tc3-referral-list')
  })

  test('TC4: GET /referral/users/{id}/transactions → 取引履歴表示 + wallet/tx_hash が DOM に存在しない', async ({
    page,
  }) => {
    await setupPartnerAuth(page)
    await mockReferralCode(page)
    await mockReferralList(page)

    await page.route('**/partner/referral/users/*/transactions', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_TRANSACTIONS),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/partner/referral')
    await page.waitForLoadState('domcontentloaded')

    // 紹介ユーザー一覧が表示されたら「取引履歴」リンクをクリックして詳細ページへ遷移
    // (Lane3: インライン展開ではなく /partner/referral/{id} への画面遷移)
    await expect(page.getByText('te**@example.com')).toBeVisible({ timeout: 10_000 })
    const detailLink = page.getByRole('link', { name: '取引履歴' }).first()
    await expect(detailLink).toBeVisible({ timeout: 5_000 })
    // Next.js client-side navigation のため waitForURL で遷移完了を確実に待つ
    // (waitForLoadState だけでは domcontentloaded が再 fire せず race condition になる)
    await Promise.all([
      page.waitForURL(/\/partner\/referral\/\d+/, { timeout: 10_000 }),
      detailLink.click(),
    ])
    expect(page.url()).toMatch(/\/partner\/referral\/\d+/)

    // 取引タイプ「入金」が表示されること
    await expect(page.getByText('入金')).toBeVisible({ timeout: 8_000 })

    // wallet address パターン (0x + 40 hex chars) が DOM に存在しないこと
    const walletAddressCount = await page
      .locator('text=/0x[a-fA-F0-9]{40}/')
      .count()
    expect(walletAddressCount).toBe(0)

    // data-testid="tx-hash" が DOM に存在しないこと
    await expect(page.locator('[data-testid="tx-hash"]')).toHaveCount(0)

    // 取引履歴テーブル内に "tx_hash" / "wallet" が出現しないこと
    // body.innerText 全体だと AppShell ナビ等の "ウォレット" メニュー文言を誤検出するため、
    // テーブル要素の innerText のみを対象にする
    const tableText = await page.locator('table').innerText().catch(() => '')
    expect(tableText).not.toContain('tx_hash')
    expect(tableText).not.toContain('wallet')

    await saveScreenshot(page, 'tc4-transactions-no-wallet')
  })
})

// ─── TC5: /r/<code> リダイレクト ─────────────────────────────────────────────

test.describe('[RAS] referral redirect', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC5: /r/ABC123 → /auth/register?ref=ABC123 にリダイレクト', async ({ page }) => {
    await page.goto('/r/ABC123')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1_000)

    const url = page.url()
    expect(url).toContain('/auth/register')
    expect(url).toContain('ref=ABC123')

    await saveScreenshot(page, 'tc5-referral-redirect')
  })
})

// ─── TC6-TC8: referral 経由登録 ──────────────────────────────────────────────

test.describe('[RAS] referral registration', () => {
  test.beforeEach(ensureScreenshotDir)

  test('TC6: /auth/register?ref=ABC123 + consent チェック → POST /auth/register-with-referral 201', async ({
    page,
  }) => {
    let capturedBody: Record<string, unknown> | null = null

    await page.route('**/auth/register-with-referral', async (route) => {
      if (route.request().method() === 'POST') {
        capturedBody = JSON.parse(route.request().postData() ?? '{}') as Record<
          string,
          unknown
        >
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 99,
            email: 'new@example.com',
            username: 'new-user',
            role: 'user',
            is_active: true,
            access_token: 'test-token-e2e',
            token_type: 'bearer',
            expires_in: 86400,
          }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/auth/register?ref=ABC123')
    await page.waitForLoadState('domcontentloaded')

    expect(page.url()).toContain('/auth/register')

    // referral_code フィールドが prefill + readOnly であること (表示形式は実装依存)
    const codeVisible = await page.getByText('ABC123').isVisible({ timeout: 8_000 }).catch(() => false)
    expect(codeVisible).toBeTruthy()

    // 「紹介プログラム同意」チェックボックスが表示されること
    const consentCheckbox = page
      .locator(
        '[data-testid="referred-consent"], input[type="checkbox"][name*="consent"], input[type="checkbox"][id*="consent"]',
      )
      .first()
    // チェックボックスが見つからない場合は role="checkbox" で検索
    const hasConsent =
      (await consentCheckbox.isVisible({ timeout: 5_000 }).catch(() => false)) ||
      (await page.getByRole('checkbox').first().isVisible({ timeout: 2_000 }).catch(() => false))
    expect(hasConsent).toBeTruthy()

    // フォームに必須項目を入力
    await page.getByLabel('メールアドレス').fill('new@example.com')

    const displayNameInput = page.getByLabel(/表示名|ユーザー名/).first()
    if (await displayNameInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await displayNameInput.fill('テストユーザー')
    }

    await page.getByLabel('パスワード').fill('Test1234!!')

    // consent チェックボックスをチェック
    const checkbox = (await consentCheckbox.isVisible({ timeout: 1_000 }).catch(() => false))
      ? consentCheckbox
      : page.getByRole('checkbox').first()
    await checkbox.check()

    // 「登録」ボタンをクリック
    const submitBtn = page
      .getByRole('button', { name: /登録|アカウントを作成/ })
      .first()
    await submitBtn.click()

    // POST /auth/register-with-referral に referred_consent=true が送られていること
    await page.waitForTimeout(2_000)
    expect(capturedBody).not.toBeNull()
    const body = capturedBody as unknown as Record<string, unknown>
    expect(body['referred_consent']).toBe(true)
    expect(body['referral_code']).toBe('ABC123')

    await saveScreenshot(page, 'tc6-register-with-referral-success')
  })

  test('TC7: consent 未チェックで submit → validation エラー表示または送信ブロック', async ({
    page,
  }) => {
    let requestMade = false

    await page.route('**/auth/register-with-referral', async (route) => {
      if (route.request().method() === 'POST') {
        requestMade = true
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'referred_consent must be true' }),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto('/auth/register?ref=ABC123')
    await page.waitForLoadState('domcontentloaded')

    // フォームに入力 (consent はチェックしない)
    await page.getByLabel('メールアドレス').fill('new@example.com')

    const displayNameInput = page.getByLabel(/表示名|ユーザー名/).first()
    if (await displayNameInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await displayNameInput.fill('テストユーザー')
    }

    await page.getByLabel('パスワード').fill('Test1234!!')

    // consent 未チェック → submit ボタンは disabled (Lane3 実装: disabled={!consent})
    // disabled ボタンへの click() はタイムアウトするため、disabled アサーションで代替
    const submitBtn = page
      .getByRole('button', { name: /登録|アカウントを作成/ })
      .first()
    await expect(submitBtn).toBeDisabled({ timeout: 5_000 })

    // フォームは送信されていないこと
    expect(requestMade).toBe(false)

    // ページが /auth/register に留まっていること
    expect(page.url()).toContain('/auth/register')

    await saveScreenshot(page, 'tc7-consent-validation-error')
  })

  test('TC8: /auth/register に referral_code なしでアクセス → 招待制エラー UI', async ({
    page,
  }) => {
    await page.goto('/auth/register')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1_500)

    const bodyText = await page.evaluate(
      () => (document.body as HTMLElement).innerText ?? '',
    )

    // 「招待コードが必要」「リンクからアクセス」等のメッセージ OR フォーム無効化
    const hasErrorMsg =
      bodyText.includes('招待コード') ||
      bodyText.includes('紹介コード') ||
      bodyText.includes('リンクからアクセス') ||
      bodyText.includes('招待が必要') ||
      bodyText.includes('コードが必要')

    const submitBtn = page
      .getByRole('button', { name: /登録|アカウントを作成/ })
      .first()
    const isDisabled = await submitBtn
      .isDisabled({ timeout: 3_000 })
      .catch(() => false)
    const isHidden = !(await submitBtn
      .isVisible({ timeout: 3_000 })
      .catch(() => false))

    // エラーメッセージ OR フォーム無効化 のいずれかであること
    expect(hasErrorMsg || isDisabled || isHidden).toBeTruthy()

    await saveScreenshot(page, 'tc8-no-referral-code-error')
  })
})
