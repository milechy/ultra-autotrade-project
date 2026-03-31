// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { test, expect } from '@playwright/test'

// ユーザーページは認証が必要な場合、ログイン画面へリダイレクトされるか
// 直接アクセスできるかを確認するスモークテスト

const USER_PAGES = [
  { path: '/user/dashboard', name: 'ダッシュボード' },
  { path: '/user/ai-feed', name: 'AI判定フィード' },
  { path: '/user/trade', name: '取引' },
  { path: '/user/history', name: '取引履歴' },
  { path: '/user/settings', name: '設定' },
  { path: '/user/copy-trading', name: 'コピートレード' },
]

for (const { path, name } of USER_PAGES) {
  test(`${name} (${path}) にアクセスしてサーバーエラーが出ない`, async ({ page }) => {
    const response = await page.goto(path)
    // 500番台のサーバーエラーでないこと（認証リダイレクト等は許容）
    expect(response?.status()).toBeLessThan(500)
  })
}
