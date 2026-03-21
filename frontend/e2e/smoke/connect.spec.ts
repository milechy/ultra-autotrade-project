// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-02 ウォレット接続 (/connect)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/connect');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/connect');
    expect(response?.status()).toBe(200);
  });

  test('「ウォレットを接続」テキストが表示される', async ({ page }) => {
    const heading = page.getByRole('heading', { name: 'ウォレットを接続' });
    await expect(heading).toBeVisible();
  });

  test('3ステップインジケーターが表示される', async ({ page }) => {
    // STEP_LABELS: ウォレット接続, ネットワーク確認, 規約同意
    await expect(page.getByText('ウォレット接続').first()).toBeVisible();
    await expect(page.getByText('ネットワーク確認')).toBeVisible();
    await expect(page.getByText('規約同意')).toBeVisible();
  });

  test('接続ボタンが表示される', async ({ page }) => {
    const connectBtn = page.getByRole('button', { name: /ウォレットを接続する/ });
    await expect(connectBtn).toBeVisible();
  });

  test('未接続状態では「運用を開始する」ボタンが表示されない', async ({ page }) => {
    // allChecksPass が false のため Start Button は非表示
    const startBtn = page.getByRole('button', { name: '運用を開始する' });
    await expect(startBtn).not.toBeVisible();
  });
});
