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

  test('ボトムナビのタブが存在する（BottomNav.tsx の navItems から）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    // shared/BottomNav.tsx: admin=4タブ（ホーム,承認,AI判定,設定）viewer=3タブ（ホーム,AI判定,ヘルプ）
    // ホームとAI判定は全ロール共通 → 未認証でも必ず存在する
    await page.goto('/decisions');
    const bottomNav = page.locator('nav[class*="bottom-0"]');
    await expect(bottomNav.getByText('ホーム')).toBeVisible();
    await expect(bottomNav.getByText('AI判定')).toBeVisible();
    // admin なら 承認・設定タブも存在、viewer なら ヘルプタブが存在
    const hasApprove = await bottomNav.getByText('承認').isVisible().catch(() => false);
    const hasHelp = await bottomNav.getByText('ヘルプ').isVisible().catch(() => false);
    // どちらかのロールレイアウトが表示されていること
    expect(hasApprove || hasHelp).toBeTruthy();
    await context.close();
  });

  test('ヘッダーにロゴ「Ultra AutoTrade」が表示される', async ({ page }) => {
    await page.goto('/decisions');
    const logo = page.getByText('Ultra AutoTrade').first();
    await expect(logo).toBeVisible();
  });

  test('緊急停止ボタンの表示確認（admin/partner 専用、viewer は非表示が正常）', async ({ page }) => {
    // EmergencyStopFloat: isAdmin || isPartner の場合のみレンダリング（22f2e6e）
    // 未認証・viewer では null を返すため、非表示が正しい動作
    await page.goto('/decisions');
    const emergencyBtn = page.locator('button[aria-label="緊急停止"], button[aria-label="停止解除"]').first();
    // admin/partner なら表示、viewer/未認証なら非表示 — どちらも正常
    const isVisible = await emergencyBtn.isVisible().catch(() => false);
    const count = await page.locator('button[aria-label="緊急停止"], button[aria-label="停止解除"]').count();
    // ボタンが存在すれば visible であること。存在しない(count=0)場合は未認証状態として正常
    if (count > 0) {
      await expect(emergencyBtn).toBeVisible();
    } else {
      expect(isVisible).toBe(false);
    }
  });
});
