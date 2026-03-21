// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-04 AI判定フィード (/decisions)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/decisions');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/decisions');
    expect(response?.status()).toBe(200);
  });

  test('ページ見出し「AI判定フィード」が表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: 'AI判定フィード' });
    await expect(heading).toBeVisible();
  });

  test('AI判定バッジ（BUY/SELL/HOLD いずれか）が存在する', async ({ page }) => {
    // MOCK_LATEST.action = 'HOLD'
    const badge = page.getByText(/BUY|SELL|HOLD/).first();
    await expect(badge).toBeVisible();
  });

  test('判定理由テキストが存在する', async ({ page }) => {
    // MOCK_LATEST.reason の一部
    const reason = page.getByText(/ボラティリティ|市場環境|ポジション/);
    await expect(reason.first()).toBeVisible();
  });

  test('判定履歴タイムラインが存在する', async ({ page }) => {
    // MOCK_HISTORY 5件分 - confidence値が表示される
    const items = page.getByText(/72%|81%|68%|75%|85%/);
    await expect(items.first()).toBeVisible();
  });
});
