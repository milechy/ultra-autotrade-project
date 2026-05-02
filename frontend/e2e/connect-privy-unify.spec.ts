// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// E2E: ユーザー登録動線の /connect 統一 (Asana GID 1214180175562193)
//
// 目的: B案改で実装した「一般ユーザーは /connect (Privy) で開始、管理者のみ
//      /register でメール登録」の動線が UI レベルで成立していることを保証する。
//
// 検証範囲:
//   1. ランディング (/) の CTA が「ウォレットで始める」 → /connect に遷移する
//   2. /register に「管理者専用」の deprecation バナーが表示され、/connect への
//      動線リンクが存在する
//   3. /connect ページのウォレット接続 UI (Privy login ボタン + ステップ
//      インジケーター) が初期表示される
//   4. tester_onboarding 途中ユーザー (メール登録済 / wallet 未接続) 向けの
//      「resume-from-email-banner」が、認証済セッションでのみ表示される
//   5. 管理者用 /login (メール/PW) のフォームは引き続き存在する
//
// Privy モーダル本体の操作 (メール OTP / wallet 作成 / signMessage) は本番の
// Privy インスタンスに依存し、CI/staging から in-line でモックできないため、
// バックエンド POST /auth/wallet/connect を route intercept でスタブし、
// 「Privy で署名済 → JWT 取得 → /user/dashboard 遷移」までをシミュレートする。
//
// 実行:
//   STAGING_URL=https://staging.ultra-auto-trade.com npx playwright test \
//     e2e/connect-privy-unify.spec.ts
//
// 既存の管理者向け email/PW テスト (smoke/landing, login など) は touched せず、
// 「管理者ロール想定」の意味づけだけここで明文化する。

import { test, expect } from '@playwright/test'

// ──────────────────────────────────────────────────────────────────────────────
// 共通ヘルパー
// ──────────────────────────────────────────────────────────────────────────────

const MOCK_JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature'

/** localStorage に有効な JWT を入れて「メール登録済 / wallet 未接続」を再現 */
async function seedAuthenticatedSession(page: import('@playwright/test').Page) {
  await page.addInitScript((token: string) => {
    const expires = Date.now() + 60 * 60 * 1000 // 1 hour
    localStorage.setItem('ultra_auth_token', token)
    localStorage.setItem('ultra_auth_expires', String(expires))
  }, MOCK_JWT)
}

/** GET /auth/me を viewer ロールで返してログイン状態を完成させる */
async function stubAuthMe(
  page: import('@playwright/test').Page,
  role: 'admin' | 'partner' | 'viewer' = 'viewer'
) {
  await page.route('**/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 99,
        email: 'tester@example.com',
        username: 'tester',
        role,
        is_active: true,
      }),
    })
  })
}

// ──────────────────────────────────────────────────────────────────────────────
// 1. ランディング → /connect 動線
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[ConnectUnify] ランディング → /connect 動線', () => {
  test('ランディングのヒーローCTAが「ウォレットで始める」になっている', async ({
    page,
  }) => {
    await page.goto('/')
    await page.waitForLoadState('domcontentloaded')

    const heroCta = page.getByRole('link', { name: 'ウォレットで始める' }).first()
    await expect(heroCta).toBeVisible()
  })

  test('「メール登録」「メールアドレスで登録」等の旧CTAは存在しない', async ({
    page,
  }) => {
    await page.goto('/')
    await page.waitForLoadState('domcontentloaded')

    // アカウント新規作成系の旧文言が hero / footer CTA で復活していないことを確認
    const heroSection = page.locator('section').first()
    const heroText = (await heroSection.textContent()) ?? ''
    expect(heroText).not.toMatch(/メール登録|メールアドレスで登録|無料登録/)
  })

  test('ヒーローCTAをクリックすると /connect に遷移する', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'ウォレットで始める' }).first().click()
    await expect(page).toHaveURL(/\/connect/)
    await expect(
      page.getByRole('heading', { name: 'ウォレットを接続' })
    ).toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 2. /register deprecation バナー
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[ConnectUnify] /register deprecation バナー', () => {
  test('/register に「管理者専用」バナーが表示される', async ({ page }) => {
    await page.goto('/register')
    await page.waitForLoadState('domcontentloaded')

    const banner = page.getByTestId('register-deprecation-banner')
    await expect(banner).toBeVisible()
    await expect(banner).toContainText('メール登録は管理者専用')
  })

  test('バナー内に /connect への動線リンクがある', async ({ page }) => {
    await page.goto('/register')
    await page.waitForLoadState('domcontentloaded')

    const link = page.getByTestId('register-banner-connect-link')
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', '/connect')
  })

  test('バナーの誘導リンクをクリックすると /connect に遷移する', async ({
    page,
  }) => {
    await page.goto('/register')
    await page.getByTestId('register-banner-connect-link').click()
    await expect(page).toHaveURL(/\/connect/)
  })

  test('カードタイトルに「管理者用」が明記されている', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByText('アカウント登録（管理者用）')).toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 3. /connect 初期 UI (Privy login ボタン)
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[ConnectUnify] /connect 初期表示', () => {
  test('「ウォレットを接続する」ボタンが表示される', async ({ page }) => {
    await page.goto('/connect')
    await expect(
      page.getByRole('button', { name: /ウォレットを接続する/ })
    ).toBeVisible()
  })

  test('3ステップインジケーター (接続 / NW / 規約) が並ぶ', async ({ page }) => {
    await page.goto('/connect')
    await expect(page.getByText('ウォレット接続').first()).toBeVisible()
    await expect(page.getByText('ネットワーク確認')).toBeVisible()
    await expect(page.getByText('規約同意')).toBeVisible()
  })

  test('未認証時は resume-from-email-banner が表示されない', async ({ page }) => {
    await page.goto('/connect')
    await expect(page.getByTestId('resume-from-email-banner')).toHaveCount(0)
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 4. tester_onboarding 途中ユーザー: 「メール登録済 / wallet 未接続」
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[ConnectUnify] resume-from-email ガイダンス', () => {
  test('viewer ロールで認証済の場合、ガイダンスバナーが表示される', async ({
    page,
  }) => {
    await stubAuthMe(page, 'viewer')
    await seedAuthenticatedSession(page)

    await page.goto('/connect')
    await page.waitForLoadState('domcontentloaded')

    const banner = page.getByTestId('resume-from-email-banner')
    await expect(banner).toBeVisible({ timeout: 10_000 })
    await expect(banner).toContainText('メール登録は完了しています')
    await expect(banner).toContainText('続けてウォレットを接続')
  })

  test('admin ロールでは resume-from-email-banner は出ない', async ({ page }) => {
    await stubAuthMe(page, 'admin')
    await seedAuthenticatedSession(page)

    await page.goto('/connect')
    await page.waitForLoadState('domcontentloaded')

    // useAuth().user の解決を待つ猶予
    await page.waitForTimeout(500)
    await expect(page.getByTestId('resume-from-email-banner')).toHaveCount(0)
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 5. 管理者向け /login (メール/PW) は維持されている
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[ConnectUnify] 管理者ログイン経路の維持', () => {
  test('/login にメール/PW フォームが存在する', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    // input[type=email] と input[type=password] が存在することで管理者経路を担保
    await expect(page.locator('input[type="email"]')).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 6. /connect → POST /auth/wallet/connect → /user/dashboard 完全フロー
//
//    Privy のモーダル操作 (OTP / 署名) は in-line でモックできないため、
//    バックエンドの /auth/wallet/connect を route intercept でスタブし、
//    「署名後に JWT が返る」「ダッシュボードに遷移する」部分の連結だけを検証する。
//    Privy SDK 自体の動作は @privy-io/react-auth が担保。
// ──────────────────────────────────────────────────────────────────────────────

test.describe('[ConnectUnify] 完全フロー (バックエンド連結確認)', () => {
  test('POST /auth/wallet/connect が成功すれば /user/dashboard に遷移する', async ({
    page,
  }) => {
    // Privy モーダルが現実環境では出るため、CI/staging で安定実行できる範囲を
    // 「バックエンド POST 成功 → router.push('/user/dashboard') が走る」までに
    // 限定する。Privy SDK 内部の処理は本テストの対象外。
    test.skip(
      true,
      'Privy モーダル経由の signMessage は CI からモック不可。staging 上で 手動回帰 (docs/22 §9) で確認する。'
    )

    let walletConnectCalled = false
    await page.route('**/auth/wallet/connect', async (route) => {
      walletConnectCalled = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: MOCK_JWT,
          token_type: 'bearer',
          expires_in: 3600,
        }),
      })
    })
    await stubAuthMe(page, 'viewer')

    await page.goto('/connect')
    // ここで Privy modal を操作する手段がないため、本来は手動回帰で確認する
    await page.waitForURL('**/user/dashboard', { timeout: 30_000 })
    expect(walletConnectCalled).toBe(true)
  })
})
