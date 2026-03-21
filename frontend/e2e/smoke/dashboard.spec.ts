// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-03 ダッシュボード (/user/dashboard)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/user/dashboard');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/user/dashboard');
    expect(response?.status()).toBe(200);
  });

  test('ウォレット未接続時に接続促すメッセージが表示される', async ({ page }) => {
    // PortfolioSummary: !isConnected → "ウォレットを接続してください"
    const msg = page.getByText('ウォレットを接続してください');
    await expect(msg).toBeVisible();
  });

  test('ポジション一覧セクションが存在する', async ({ page }) => {
    const section = page.getByText('ポジション一覧');
    await expect(section).toBeVisible();
  });

  test('資産推移チャートセクションが存在する', async ({ page }) => {
    const section = page.getByText('資産推移');
    await expect(section).toBeVisible();
  });

  test('最新AI判定セクションが存在する', async ({ page }) => {
    const section = page.getByText('最新AI判定');
    await expect(section).toBeVisible();
  });

  test('ヘッダーにロゴが表示される', async ({ page }) => {
    const logo = page.getByText('Ultra AutoTrade').first();
    await expect(logo).toBeVisible();
  });
});
