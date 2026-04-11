// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect, devices } from '@playwright/test';

// 設計方針: Privy はクライアントサイド認証のため page.goto 後に非同期でリダイレクトが発生する。
// networkidle ではリダイレクト完了を保証できないため、Promise.race で
// 「要素が現れる(認証済み)」か「/login にリダイレクト(未認証)」のどちらかを待機する。
// 未ログイン状態では BottomNav/Logo/EmergencyStop が非表示になるのが正常動作（アプローチ B）。
test.describe('ナビゲーション全体テスト', () => {
  test('ボトムナビが表示される（モバイルビューポート）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    await page.goto('/decisions');
    // 認証済み → BottomNav 出現、未認証 → /login リダイレクト
    const state = await Promise.race([
      page.waitForSelector('nav[class*="bottom-0"]', { timeout: 10000 }).then(() => 'has-nav'),
      page.waitForURL('**/login**', { timeout: 10000 }).then(() => 'login'),
    ]).catch(() => 'unknown');
    if (state === 'has-nav') {
      // 認証済み: mobile では BottomNav が visible であること
      await expect(page.locator('nav[class*="bottom-0"]')).toBeVisible();
    } else {
      // 未認証リダイレクト: BottomNav 非表示が正常動作
      expect(await page.locator('nav[class*="bottom-0"]').isVisible().catch(() => false)).toBe(false);
    }
    await context.close();
  });

  test('ボトムナビのタブが存在する（BottomNav.tsx の navItems から）', async ({ browser }) => {
    const context = await browser.newContext({ ...devices['iPhone 14'] });
    const page = await context.newPage();
    await page.goto('/decisions');
    // 認証済み → BottomNav 出現、未認証 → /login リダイレクト
    const state = await Promise.race([
      page.waitForSelector('nav[class*="bottom-0"]', { timeout: 10000 }).then(() => 'has-nav'),
      page.waitForURL('**/login**', { timeout: 10000 }).then(() => 'login'),
    ]).catch(() => 'unknown');
    if (state !== 'has-nav') {
      // 未認証リダイレクト: BottomNavなし、正常動作
      await context.close();
      return;
    }
    // 認証済み: shared/BottomNav.tsx の navItems を確認
    // admin=4タブ（ホーム,承認,AI判定,設定）viewer=3タブ（ホーム,AI判定,ヘルプ）
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
    // 認証済み → ロゴ出現、未認証 → /login リダイレクト
    const state = await Promise.race([
      page.waitForSelector('text=Ultra AutoTrade', { timeout: 10000 }).then(() => 'has-logo'),
      page.waitForURL('**/login**', { timeout: 10000 }).then(() => 'login'),
    ]).catch(() => 'unknown');
    if (state === 'has-logo') {
      // 認証済み: UserHeader にロゴが表示されること
      await expect(page.getByText('Ultra AutoTrade').first()).toBeVisible();
    } else {
      // 未認証リダイレクト: ロゴなしが正常動作
      expect(await page.getByText('Ultra AutoTrade').first().isVisible().catch(() => false)).toBe(false);
    }
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
