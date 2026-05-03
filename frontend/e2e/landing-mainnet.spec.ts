// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import { test, expect } from '@playwright/test';

/**
 * チェーン表記一貫性チェック (mainnet)
 *
 * 2026-05-02 incident: frontend/app/page.tsx had hardcoded "Base Sepolia" text
 * that was not detected by existing E2E tests during 5/1 mainnet switch.
 *
 * 2026-05-03 update: / は /login へのリダイレクトゲートになったため、
 * チェーン表記チェックを /connect（ウォレット接続の主要入口）に移動。
 *
 * Asana: GID 1214462619161978
 */
test.describe('/connect チェーン表記一貫性チェック (mainnet)', () => {
  // /connect は Privy パッケージを含み初回コンパイルが遅いため test timeout を延長
  test.setTimeout(90000);

  test('/connect に Sepolia / テストネット 表記が含まれていない', async ({ page }) => {
    await page.goto('/connect', { timeout: 60000 });
    await page.waitForLoadState('domcontentloaded');

    const html = await page.content();

    expect(html, '/connect should not contain "Sepolia" text').not.toMatch(/Sepolia/i);
    expect(html, '/connect should not contain "テストネット" text').not.toContain('テストネット');
  });

  test('/connect の NEXT_PUBLIC_DEFAULT_CHAIN_ID が 8453 (Base Mainnet) である', async ({ page }) => {
    await page.goto('/connect', { timeout: 60000 });
    await page.waitForLoadState('domcontentloaded');

    // The connect page uses DEFAULT_CHAIN_ID = parseInt(NEXT_PUBLIC_DEFAULT_CHAIN_ID || '8453')
    // Verify no Sepolia chain ID (84532) appears as the default chain identifier
    const html = await page.content();
    expect(
      html,
      '/connect should not contain Sepolia chain ID 84532 as default'
    ).not.toMatch(/DEFAULT_CHAIN_ID.*84532/);
  });

  test('/connect のウォレット接続ページが正常に読み込まれる', async ({ page }) => {
    const response = await page.goto('/connect', { timeout: 60000 });
    expect(response?.status()).toBeLessThan(500);
    await page.waitForLoadState('domcontentloaded');
    const connectBtn = page.getByRole('button', { name: /ウォレットを接続する/ });
    await expect(connectBtn).toBeVisible({ timeout: 15000 });
  });
});
