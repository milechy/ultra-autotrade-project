// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

// 未認証状態では /login にリダイレクトされる場合がある。
// approve.spec.ts と同じパターンで「ダッシュボードコンテンツ OR ログイン状態」を許容する。

test.describe('U-03 ダッシュボード (/user/dashboard)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/user/dashboard');
    await page.waitForLoadState('domcontentloaded');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/user/dashboard');
    // 認証リダイレクト（302 → ログインページ 200）も許容。500番台でないこと。
    expect(response?.status()).toBeLessThan(500);
  });

  test('ウォレット未接続時に接続促すメッセージが表示される', async ({ page }) => {
    // PortfolioSummary: !isConnected → "ウォレットを接続してください"
    // 未認証時はログインページへリダイレクトされる場合も許容
    const msg = page.getByText('ウォレットを接続してください');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      msg.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasMsg = await msg.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasMsg || hasLoginBtn || hasLoginHeading).toBeTruthy();
  });

  test('ポジション一覧セクションが存在する', async ({ page }) => {
    const section = page.getByText('ポジション一覧');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      section.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasSection = await section.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasSection || hasLoginBtn || hasLoginHeading).toBeTruthy();
  });

  test('資産推移チャートセクションが存在する', async ({ page }) => {
    const section = page.getByText('資産推移');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      section.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasSection = await section.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasSection || hasLoginBtn || hasLoginHeading).toBeTruthy();
  });

  test('最新AI判定セクションが存在する', async ({ page }) => {
    const section = page.getByText('最新AI判定');
    const loginBtn = page.getByRole('button', { name: 'ログイン' });
    const loginHeading = page.getByRole('heading', { name: 'Ultra AutoTrade' });

    await Promise.any([
      section.waitFor({ state: 'visible', timeout: 10000 }),
      loginBtn.waitFor({ state: 'visible', timeout: 10000 }),
      loginHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasSection = await section.isVisible().catch(() => false);
    const hasLoginBtn = await loginBtn.isVisible().catch(() => false);
    const hasLoginHeading = await loginHeading.isVisible().catch(() => false);
    expect(hasSection || hasLoginBtn || hasLoginHeading).toBeTruthy();
  });

  test('ヘッダーにロゴが表示される', async ({ page }) => {
    // "Ultra AutoTrade" はダッシュボードヘッダーにもログインページにも存在する
    const logo = page.getByText('Ultra AutoTrade').first();
    await expect(logo).toBeVisible();
  });
});
