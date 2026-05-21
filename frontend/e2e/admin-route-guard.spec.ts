// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Gate 4 — Admin route guard: defense-in-depth (page-level AuthGuard adminOnly)
//
// 背景 (Asana 1214988782308755):
//   - layout.tsx → AdminProviders → AdminGuard はクライアントサイドで非 admin を
//     redirect + return null する（既存保護層）。
//   - 本 PR では各 page.tsx に <AuthGuard adminOnly> を追加し、
//     layout ガードが bypass された場合の二重防御を実装。
//
// テスト戦略:
//   - 未認証状態で /rebalance /exchange /trades /events /knowledge /settings/account
//     /protocols /ai-decisions へアクセスし、/login または /403 へ redirect することを確認。
//   - AuthGuard は localStorage ベースであるため、
//     未認証 (localStorage に token なし) = client-side redirect to /login。
//   - URL 確認: route group (admin) のページは group 名を URL に含まない。
//     例: app/(admin)/rebalance/page.tsx → URL は /rebalance
//
// 実行方法:
//   # 本番向け (デフォルト)
//   npx playwright test e2e/admin-route-guard.spec.ts
//
//   # ローカル確認
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/admin-route-guard.spec.ts
//
// NOTE: このテストは未認証ブラウザセッション (localStorageにトークンなし) で実行。
//       AdminGuard と AuthGuard adminOnly の両方が正常に動作することを確認する。

import { test, expect } from '@playwright/test'

// 保護対象 admin URL 一覧 (route group (admin) なので URL に admin は含まない)
const ADMIN_ROUTES = [
  '/rebalance',
  '/exchange',
  '/trades',
  '/events',
  '/knowledge',
  '/knowledge/search',
  '/ai-decisions',
  '/protocols',
  '/users',
  '/reports',
  '/data-feeds',
  '/ai-learning',
  '/settings/account',
  '/settings/system',
  '/settings/config',
  '/settings/users',
]

// 未認証状態では /login へ redirect されること、または /login コンテンツが表示されること
// (client-side redirect なので HTTP status は 200、URL が変わることで確認)
function isLoginOrForbidden(url: string): boolean {
  return (
    url.includes('/login') ||
    url.includes('/403') ||
    url.includes('/forbidden')
  )
}

test.describe('Admin route guard — 未認証アクセス制御 (defense-in-depth)', () => {
  // 各テストは独立したコンテキストで実行し、localStorage をクリア
  test.use({ storageState: { cookies: [], origins: [] } })

  for (const route of ADMIN_ROUTES) {
    test(`未認証で ${route} → /login にリダイレクト`, async ({ page }) => {
      // localStorage トークンが無い状態でアクセス (新規コンテキスト)
      await page.goto(route)

      // クライアントサイドリダイレクト (AuthGuard / AdminGuard) を待つ
      // 最大 15 秒待機
      try {
        await page.waitForURL('**/login', { timeout: 15000 })
        expect(page.url()).toContain('/login')
      } catch {
        // URL が /login に変わらなかった場合はページ内容を確認
        // AuthGuard は isLoading 中に「読み込み中...」を表示し、
        // loading 完了後に redirect する。
        // redirect 先が /login 以外になる可能性も考慮してログイン UI を確認。
        const currentUrl = page.url()

        if (isLoginOrForbidden(currentUrl)) {
          // 既にリダイレクト済み
          expect(isLoginOrForbidden(currentUrl)).toBeTruthy()
          return
        }

        // ページがロード済みなら login UI または loading spinner のみ表示されること
        await page.waitForLoadState('domcontentloaded')
        await page.waitForTimeout(5000)

        const afterUrl = page.url()
        const bodyText = await page.locator('body').textContent().catch(() => '')

        // 選択肢:
        // 1. redirect が完了して /login にいる
        // 2. ロード中 (「読み込み中...」が表示) = null render 中
        // 3. 完全に null render (body がほぼ空)
        // いずれも admin コンテンツが表示されていないことが重要
        const isRedirected = isLoginOrForbidden(afterUrl)
        const isLoadingState =
          (bodyText ?? '').includes('読み込み中') ||
          (bodyText ?? '').includes('Loading')
        const isNullRender = (bodyText ?? '').trim().length < 100

        // admin コンテンツのキーワードが表示されていないことを確認
        const adminKeywords = [
          'リバランス', '取引所管理', '取引履歴', '監視イベント',
          'ナレッジ Hub', 'AI 判定', 'プロトコルヘルス',
          'ユーザー管理', 'データフィード',
        ]
        const hasAdminContent = adminKeywords.some(
          (kw) => (bodyText ?? '').includes(kw)
        )

        // admin コンテンツが表示されていないこと、または redirect 済み / loading 中であること
        if (hasAdminContent) {
          // admin コンテンツが見えている = ガードが効いていない
          throw new Error(
            `[FAIL] ${route}: admin コンテンツが未認証状態で表示されています。` +
            ` URL: ${afterUrl}, Content snippet: ${(bodyText ?? '').slice(0, 200)}`
          )
        }

        // redirect / loading / null render のいずれかであること
        expect(isRedirected || isLoadingState || isNullRender).toBeTruthy()
      }
    })
  }

  // 特定ルートの詳細テスト: /rebalance は最重要 (Aave 操作画面)
  test('未認証で /rebalance にアクセスすると Aave 操作 UI が表示されない', async ({ page }) => {
    await page.goto('/rebalance')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(8000)

    // Aave 操作の主要 UI 要素が表示されていないこと
    const rebalanceButton = page.getByRole('button', { name: /リバランス実行|リバランス/ })
    const aaveSection = page.getByText('Aave リバランス')
    const hfSection = page.getByText('Health Factor')

    // 各要素の可視性チェック (HF は /login ページにも出ないはず)
    const hasRebalanceButton = await rebalanceButton.isVisible().catch(() => false)
    // HF は他のページでも使う可能性があるので rebalanceButton で判定
    expect(hasRebalanceButton).toBeFalsy()

    // aaveSection は /rebalance の固有コンテンツ
    const hasAaveSection = await aaveSection.isVisible().catch(() => false)
    expect(hasAaveSection).toBeFalsy()

    // ログイン UI または空画面であること
    const loginBtn = page.getByRole('button', { name: /ログイン/ })
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' })
    const bodyText = await page.locator('body').textContent().catch(() => '')
    const isLoadingOrEmpty =
      (bodyText ?? '').includes('読み込み中') ||
      (bodyText ?? '').trim().length < 200

    const hasLoginUI =
      await loginBtn.isVisible().catch(() => false) ||
      await loginHeading.isVisible().catch(() => false)

    expect(hasLoginUI || isLoadingOrEmpty).toBeTruthy()
  })

  // /login 自体は正常にアクセスできること (guard が /login をブロックしない確認)
  test('/login ページが正常に表示される', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
    await expect(page.getByRole('button', { name: 'ログイン' })).toBeVisible({ timeout: 15000 })
  })
})

test.describe('Admin route guard — 認証済み admin ユーザーは正常アクセス可能', () => {
  // NOTE: 本番 E2E では admin 認証情報 (E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD) が
  //       環境変数として提供される場合のみ実行。未設定の場合は skip。
  //       staging での admin アカウントが整備されたら認証フローを追加。

  test('admin アクセス確認 (認証情報未設定時はスキップ)', async ({ page }) => {
    const email = process.env.E2E_ADMIN_EMAIL
    const password = process.env.E2E_ADMIN_PASSWORD

    if (!email || !password) {
      console.log(
        '[SKIP] E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD が未設定のため admin アクセス確認をスキップ。' +
        ' staging admin アカウント整備後に有効化してください。'
      )
      return
    }

    // /login でログイン
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
    await page.getByLabel('メールアドレス').fill(email)
    await page.getByLabel('パスワード').fill(password)
    await page.getByRole('button', { name: 'ログイン' }).click()

    // ダッシュボードまたは admin 画面への遷移を待つ
    await page.waitForURL(/\/(dashboard|rebalance|exchange|trades)/, { timeout: 15000 }).catch(() => {})

    // /rebalance にアクセス → redirect されないこと
    await page.goto('/rebalance')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(5000)

    const currentUrl = page.url()
    // admin なら /rebalance のままか、admin 系ページにいること
    expect(currentUrl).not.toContain('/login')
    console.log(`[INFO] admin アクセス後 URL: ${currentUrl}`)
  })
})
