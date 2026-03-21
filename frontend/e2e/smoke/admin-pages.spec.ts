// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
import { test, expect } from '@playwright/test'

const ADMIN_PAGES = [
  { path: '/admin/dashboard', name: '管理ダッシュボード' },
  { path: '/admin/ai-decisions', name: 'AI判定ログ' },
  { path: '/admin/knowledge', name: 'ナレッジハブ' },
  { path: '/admin/exchange', name: '取引所' },
  { path: '/admin/rebalance', name: 'リバランス' },
  { path: '/components-preview', name: 'コンポーネントプレビュー' },
]

for (const { path, name } of ADMIN_PAGES) {
  test(`${name} (${path}) にアクセスしてサーバーエラーが出ない`, async ({ page }) => {
    const response = await page.goto(path)
    expect(response?.status()).toBeLessThan(500)
  })
}
