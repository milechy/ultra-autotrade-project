// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
//
// Gate 4 — 未認証ユーザー導線テスト
//
// 背景: 2026-05-03 山本さん（本番テスター）が / で詰まった。
//       トップページから /login への導線が欠落していた。
//       本テストでリグレッションを防ぐ。
//
// 実行方法:
//   # 本番向け (デフォルト)
//   npx playwright test e2e/unauth-flow.spec.ts
//
//   # ローカル確認
//   STAGING_URL=http://localhost:3000 npx playwright test e2e/unauth-flow.spec.ts

import { test, expect } from '@playwright/test'

test.describe('未認証ユーザー導線 (Gate 4)', () => {
  // TC1: / → /login リダイレクト
  test('TC1: 未認証で / にアクセスすると /login にリダイレクトされる', async ({ page }) => {
    await page.goto('/')
    // クライアントサイドリダイレクト（AuthProvider初期化後に発火）を待つ
    await page.waitForURL('**/login', { timeout: 15000 })
    expect(page.url()).toContain('/login')
  })

  // TC2: /login にメール/パスワードフォームが表示される
  test('TC2: /login でメール/パスワードフォームが表示される', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    // ログインカードのタイトル
    await expect(page.getByText('Ultra AutoTrade')).toBeVisible()
    // メールアドレス入力
    await expect(page.getByLabel('メールアドレス')).toBeVisible()
    // パスワード入力
    await expect(page.getByLabel('パスワード')).toBeVisible()
    // ログインボタン
    await expect(page.getByRole('button', { name: 'ログイン' })).toBeVisible()
  })

  // TC3: /connect に直接アクセスするとウォレット接続UIが表示される（既存フロー維持確認）
  // NOTE: /connect は Privy を使用しており外部リクエストが発生するため networkidle を使わない。
  //       ヘッダーは SSR で描画されるため domcontentloaded 後に検出可能。
  test('TC3: /connect にアクセスするとウォレット接続UIが表示される', async ({ page }) => {
    await page.goto('/connect')
    // ウォレット接続ヘッダー（静的 SSR レンダリング）
    await expect(page.getByRole('heading', { name: 'ウォレットを接続' })).toBeVisible({ timeout: 30000 })
  })

  // TC4: モバイル（375px）でも / → /login リダイレクトが動作する
  test('TC4: モバイルで未認証 / → /login リダイレクトが動作する', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await page.waitForURL('**/login', { timeout: 15000 })
    expect(page.url()).toContain('/login')

    // /login のフォームがモバイルでも表示される
    await expect(page.getByRole('button', { name: 'ログイン' })).toBeVisible()
  })
})
