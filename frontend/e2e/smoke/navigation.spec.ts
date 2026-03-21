// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect, devices } from '@playwright/test';

test.describe('ナビゲーション全体テスト', () => {
  test('ボトムナビが表示される（モバイルビューポート）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    await page.goto('/user/dashboard');
    // BottomNav: md:hidden のため mobile でのみ表示
    const nav = page.locator('nav').filter({ hasText: /ダッシュボード/ });
    await expect(nav).toBeVisible();
    await context.close();
  });

  test('ボトムナビの5タブが存在する（BottomNav.tsx の navItems から）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    await page.goto('/user/dashboard');
    // navItems: ダッシュボード, AI, 承認, 履歴, 設定
    await expect(page.getByText('ダッシュボード')).toBeVisible();
    await expect(page.getByText('AI').first()).toBeVisible();
    await expect(page.getByText('承認')).toBeVisible();
    await expect(page.getByText('履歴')).toBeVisible();
    await expect(page.getByText('設定')).toBeVisible();
    await context.close();
  });

  test('ヘッダーにロゴ「Ultra AutoTrade」が表示される', async ({ page }) => {
    await page.goto('/user/dashboard');
    const logo = page.getByText('Ultra AutoTrade').first();
    await expect(logo).toBeVisible();
  });

  test('緊急停止ボタンが表示される（フローティング）', async ({ page }) => {
    await page.goto('/user/dashboard');
    // EmergencyStopButton: テキスト「緊急停止」
    const emergencyBtn = page.getByRole('button', { name: '緊急停止' });
    await expect(emergencyBtn).toBeVisible();
  });
});
