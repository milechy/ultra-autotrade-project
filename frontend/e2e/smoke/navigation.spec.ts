// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect, devices } from '@playwright/test';

// /user/dashboard は (user) グループ外のため UserLayout が適用されない。
// BottomNav/Header のテストは (user) グループ内のページ（/decisions）で行う。
test.describe('ナビゲーション全体テスト', () => {
  test('ボトムナビが表示される（モバイルビューポート）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    // /decisions は (user) グループ内 → UserLayout（BottomNav付き）が適用される
    await page.goto('/decisions');
    // BottomNav: fixed bottom-0, md:hidden → mobile では visible
    const nav = page.locator('nav[class*="bottom-0"]');
    await expect(nav).toBeVisible();
    await context.close();
  });

  test('ボトムナビの5タブが存在する（BottomNav.tsx の navItems から）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    await page.goto('/decisions');
    // BottomNav 内のリンクを特定して検証
    const bottomNav = page.locator('nav[class*="bottom-0"]');
    await expect(bottomNav.getByText('ダッシュボード')).toBeVisible();
    await expect(bottomNav.getByText('AI')).toBeVisible();
    await expect(bottomNav.getByText('承認')).toBeVisible();
    await expect(bottomNav.getByText('履歴')).toBeVisible();
    await expect(bottomNav.getByText('設定')).toBeVisible();
    await context.close();
  });

  test('ヘッダーにロゴ「Ultra AutoTrade」が表示される', async ({ page }) => {
    await page.goto('/decisions');
    const logo = page.getByText('Ultra AutoTrade').first();
    await expect(logo).toBeVisible();
  });

  test('緊急停止ボタンが表示される（フローティング）', async ({ page }) => {
    await page.goto('/decisions');
    // UserLayout: <div class="fixed bottom-20 right-4 z-50"> 内の EmergencyStopButton (variant=inline)
    const floatingContainer = page.locator('div[class*="bottom-20"]');
    const emergencyBtn = floatingContainer.getByRole('button', { name: '緊急停止' });
    await expect(emergencyBtn).toBeVisible();
  });
});
