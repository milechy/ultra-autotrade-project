// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

test.describe('U-07 設定 (/settings)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('ページが200で読み込まれる', async ({ page }) => {
    const response = await page.goto('/settings');
    expect(response?.status()).toBe(200);
  });

  test('ページ見出し「設定」が表示される', async ({ page }) => {
    // exact: true で「リスク設定」「通知設定」を除外
    const heading = page.getByRole('heading', { name: '設定', exact: true });
    await expect(heading).toBeVisible();
  });

  test('運用モードセクションが存在する', async ({ page }) => {
    // OperationModeCard
    const section = page.getByText('運用モード');
    await expect(section.first()).toBeVisible();
  });

  test('リスク設定セクションが存在する', async ({ page }) => {
    // RiskSettingsCard
    const section = page.getByText('リスク設定');
    await expect(section.first()).toBeVisible();
  });

  test('通知設定セクションが存在する', async ({ page }) => {
    // NotificationCard
    const section = page.getByText('通知設定');
    await expect(section.first()).toBeVisible();
  });

  test('ウォレット情報セクションが存在する', async ({ page }) => {
    // WalletInfoCard: CardTitle は h3 として 'ウォレット' を表示する
    // ナビリンク（/user/wallet の <a>）も 'ウォレット' を含むが hidden なため、
    // role=heading でフィルタリングして visible な CardTitle（h3）のみを対象にする
    const section = page.getByRole('heading', { name: 'ウォレット', exact: true });
    await expect(section.first()).toBeVisible();
  });

  test('アプリ情報セクションが存在する', async ({ page }) => {
    // AppInfoCard: "アプリ情報" と "v0.1.0-staging"
    const section = page.getByText('アプリ情報');
    await expect(section).toBeVisible();
    const version = page.getByText('v0.1.0-staging');
    await expect(version).toBeVisible();
  });
});
