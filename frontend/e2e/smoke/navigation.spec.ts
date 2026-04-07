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

  test('ボトムナビの4タブが存在する（BottomNav.tsx の navItems から）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    // shared/BottomNav.tsx: navItems = ホーム, 承認, AI判定, 設定 (4タブ)
    // /decisions は (user) グループ内かつ未認証リダイレクトなし → UserLayout が適用される
    await page.goto('/decisions');
    // BottomNav: fixed bottom-0, md:hidden → mobile では visible
    const bottomNav = page.locator('nav[class*="bottom-0"]');
    await expect(bottomNav.getByText('ホーム')).toBeVisible();
    await expect(bottomNav.getByText('承認')).toBeVisible();
    await expect(bottomNav.getByText('AI判定')).toBeVisible();
    await expect(bottomNav.getByText('設定')).toBeVisible();
    await context.close();
  });

  test('ヘッダーにロゴ「Ultra AutoTrade」が表示される', async ({ page }) => {
    await page.goto('/decisions');
    const logo = page.getByText('Ultra AutoTrade').first();
    await expect(logo).toBeVisible();
  });

  test('緊急停止ボタンが表示される（フローティング）', async ({ page }) => {
    // /decisions は (user) グループ内かつ未認証リダイレクトなし → EmergencyStopFloat が適用される
    await page.goto('/decisions');
    // EmergencyStopFloat: aria-label は isStopped によって「緊急停止」または「停止解除」に変わる
    const emergencyBtn = page.locator('button[aria-label="緊急停止"], button[aria-label="停止解除"]').first();
    await expect(emergencyBtn).toBeVisible();
  });
});
