// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
/**
 * E2E spec: AI Optimizer 戦略推奨カード (OptimizerCard) smoke test
 * Asana: 1216340622195023 (Tier B)
 *
 * 背景:
 *   backend `POST /api/ai/optimizer/recommend` は #851 (feat/audit: AI Optimizer
 *   戦略推奨を UI 配線) で既に frontend/lib/api/optimizer.ts + OptimizerCard.tsx
 *   として実装済み・`/user/dashboard` (Managed/Active 両 variant) に配線済み。
 *   本 spec はその配線が実機ブラウザ上で機能することを確認する回帰テスト
 *   (配線当時に E2E が書かれていなかったギャップを埋める)。
 *
 * NOTE:
 *   - `(user)/strategies` は route group で URL は `/strategies` になるが、
 *     BottomNav (frontend/components/shared/BottomNav.tsx) の nav 項目には
 *     含まれない orphan page。実際に nav (admin/viewer 双方の home 項目) から
 *     到達可能な URL は `/user/dashboard` のため、本 spec はそちらへ遷移する。
 *   - フル Privy ログインは E2E 環境で安定操作不可のため、認証ゲートで
 *     /login にリダイレクトされる場合は e2e/strategies-i18n.spec.ts /
 *     e2e/smoke/dashboard.spec.ts と同じ「到達可否を許容し gracefully skip する」
 *     パターンに合わせる。
 *
 *   ローカル検証 (このタスクの一環で実施済み):
 *     backend を `INITIAL_ADMIN_EMAIL` 付きで起動 → `/auth/register` で実ユーザーを
 *     作成 → `/auth/terms/accept` → 実 JWT を localStorage に注入した状態で
 *     `/user/dashboard` にアクセスしたところ、OptimizerCard は正しく描画され
 *     (タイトル "最適配分を試算" を含む)、`POST /api/ai/optimizer/recommend`
 *     (Next proxy 経由) が実 backend から 200 を返すことを確認済み。
 *     ただしこの sandbox VM は headless Chromium のソフトウェア GL 描画が非力なため、
 *     認証済みダッシュボード全体 (recharts 込み) を継続レンダリングすると
 *     renderer が crash する既知の環境制約があり (本 spec / OptimizerCard 固有の
 *     問題ではない — 未認証時の同ページや `/strategies` は crash しない)、
 *     CI 向けの本 spec では決定論的な mock 認証には依存せず、到達可否ベースの
 *     skip 許容パターンを採用する。
 */

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const DASHBOARD_URL = '/user/dashboard'

/** /user/dashboard に遷移し、認証ゲートを回避せず到達できたかを返す */
async function visitDashboard(page: Page): Promise<boolean> {
  const res = await page.goto(DASHBOARD_URL, { waitUntil: 'domcontentloaded' })
  if (!res || res.status() >= 500) return false
  if (!page.url().includes('/user/dashboard')) return false
  return true
}

test.describe('[ai-optimizer] AI 推奨配分カード (/user/dashboard)', () => {
  test('TC1: /user/dashboard が 404/5xx を返さない', async ({ page }) => {
    const res = await page.goto(DASHBOARD_URL, { waitUntil: 'domcontentloaded' })
    expect(res, 'navigation response should exist').not.toBeNull()
    expect(res!.status(), '/user/dashboard は 404 であってはならない').not.toBe(404)
    expect(res!.status(), '/user/dashboard は 5xx であってはならない').toBeLessThan(500)
  })

  test('TC2: 最適配分カードが表示され、リスクモード切替 + 推奨取得が動作する', async ({ page }) => {
    const reachable = await visitDashboard(page)
    test.skip(!reachable, '認証ゲートで /user/dashboard に到達不能のため skip')

    const card = page.getByTestId('optimizer-card').first()
    const cardVisible = await card
      .waitFor({ state: 'visible', timeout: 10000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!cardVisible, 'ウォレット未接続 / 未認証でカードが描画されないため skip')

    // カードタイトル (Strategies.optimizer.title = "最適配分を試算")
    await expect(card.getByText('最適配分を試算')).toBeVisible()

    // リスクモード切替: balanced を選択（デフォルトは conservative）
    const balancedBtn = card.getByTestId('optimizer-risk-balanced')
    await expect(balancedBtn).toBeVisible()
    await balancedBtn.click()

    // 推奨取得ボタン押下 → POST /api/ai/optimizer/recommend (プロキシ経由) が
    // 200 を返すことを確認する
    const submitBtn = card.getByTestId('optimizer-submit')
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/optimizer/recommend') && res.request().method() === 'POST',
        { timeout: 15000 },
      ),
      submitBtn.click(),
    ])
    expect(response.status(), 'AI optimizer API は 200 を返すべき').toBe(200)

    // 結果 (推奨戦略 + 配分テーブル) が描画されることを確認
    const result = card.getByTestId('optimizer-result')
    await expect(result).toBeVisible({ timeout: 10000 })

    // aggressive に切り替えて再取得しても UI が更新されることを確認
    const aggressiveBtn = card.getByTestId('optimizer-risk-aggressive')
    await aggressiveBtn.click()
    const [response2] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/optimizer/recommend') && res.request().method() === 'POST',
        { timeout: 15000 },
      ),
      submitBtn.click(),
    ])
    expect(response2.status(), 'risk_mode 切替後の再取得も 200 を返すべき').toBe(200)
    await expect(result).toBeVisible({ timeout: 10000 })
  })
})
