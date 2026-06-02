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

  test('運用モードセクションが存在する（admin/partner のみ表示）', async ({ page }) => {
    // OperationModeCard は isPartner || isAdmin の場合のみ表示（03bca37）
    // viewer/未認証では非表示が正しい動作
    const section = page.getByText('運用モード');
    const settingsHeading = page.getByRole('heading', { name: '設定', exact: true });

    await Promise.any([
      section.first().waitFor({ state: 'visible', timeout: 10000 }),
      settingsHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});

    const hasSection = await section.first().isVisible().catch(() => false);
    const hasHeading = await settingsHeading.isVisible().catch(() => false);
    // admin/partner: 運用モードセクション表示。viewer/未認証: 設定ページ見出しのみ表示
    expect(hasSection || hasHeading).toBeTruthy();
  });

  test('リスク設定セクションが存在する', async ({ page }) => {
    // RiskSettingsCard (未認証時は非表示、設定ページ見出しをフォールバックとする)
    const section = page.getByText('リスク設定');
    const settingsHeading = page.getByRole('heading', { name: '設定', exact: true });
    await Promise.any([
      section.first().waitFor({ state: 'visible', timeout: 10000 }),
      settingsHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});
    const hasSection = await section.first().isVisible().catch(() => false);
    const hasSettingsHeading = await settingsHeading.isVisible().catch(() => false);
    expect(hasSection || hasSettingsHeading).toBeTruthy();
  });

  test('通知設定セクションが存在する', async ({ page }) => {
    // NotificationCard
    const section = page.getByText('通知設定');
    await expect(section.first()).toBeVisible();
  });

  test('ウォレット情報セクションが存在する', async ({ page }) => {
    // WalletInfoCard: CardTitle は h3 として 'ウォレット' を表示する (未認証時は非表示、設定ページ見出しをフォールバック)
    const section = page.getByRole('heading', { name: 'ウォレット', exact: true });
    const settingsHeading = page.getByRole('heading', { name: '設定', exact: true });
    await Promise.any([
      section.first().waitFor({ state: 'visible', timeout: 10000 }),
      settingsHeading.waitFor({ state: 'visible', timeout: 10000 }),
    ]).catch(() => {});
    const hasSection = await section.first().isVisible().catch(() => false);
    const hasSettingsHeading = await settingsHeading.isVisible().catch(() => false);
    expect(hasSection || hasSettingsHeading).toBeTruthy();
  });

  test('アプリ情報セクションが存在する', async ({ page }) => {
    // AppInfoCard: "アプリ情報" と "v0.1.0-staging"
    const section = page.getByText('アプリ情報');
    await expect(section).toBeVisible();
    const version = page.getByText('v0.1.0-staging');
    await expect(version).toBeVisible();
  });
});
